"""Dex device-flow tokens for the GlueOps toolbox.

Everything behind the GlueOps edge (oauth2-proxy) will accept a Dex-issued
id_token in place of a browser session cookie. This module obtains one and keeps
it fresh, so the CLIs in this image can be used normally.

The device flow is deliberate: it needs no loopback listener and no redirect URI,
so it works from inside a container whose browser lives on the host.

stdlib only.
"""

import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Refresh early rather than hand out a token that expires mid-request.
EXPIRY_SKEW = 60


def _env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        sys.exit(f"toolbox: {name} is not set (see README)")
    return v


def captain_domain():
    return _env("TOOLBOX_CAPTAIN_DOMAIN", required=True)


def dex_url():
    return _env("TOOLBOX_DEX_URL") or f"https://dex.{captain_domain()}"


def client_id():
    return _env("TOOLBOX_CLIENT_ID", "toolbox")


def cache_path():
    return os.path.expanduser(
        _env("TOOLBOX_TOKEN_CACHE", "~/.config/glueops/toolbox-token.json")
    )


def log(msg):
    print(msg, file=sys.stderr)


def _post(path, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(dex_url() + path, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode(errors="replace")[:200]}
    except urllib.error.URLError as e:
        sys.exit(f"toolbox: cannot reach Dex at {dex_url()}: {e.reason}")


def _read_cache():
    try:
        with open(cache_path()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_cache(obj):
    p = cache_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # it is a credential
    os.replace(tmp, p)


def _expiry(token):
    """`exp` from a JWT, unverified - verification is the server's job. We only
    need to know whether it is still worth sending."""
    try:
        import base64

        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0)
    except Exception:
        return 0


def _valid(token):
    return bool(token) and _expiry(token) - EXPIRY_SKEW > time.time()


def _refresh(refresh_token, quiet=False):
    status, body = _post(
        "/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id(),
        },
    )
    if status == 200 and body.get("id_token"):
        return body
    if not quiet:
        log(f"toolbox: refresh failed ({status}); falling back to a browser login")
    return None


def _device_flow():
    status, body = _post(
        "/device/code",
        {
            "client_id": client_id(),
            "scope": "openid profile email groups offline_access",
        },
    )
    if status != 200:
        sys.exit(f"toolbox: could not start device flow: {status} {body}")

    log("")
    log("  Open this URL in your browser and approve with GitHub:")
    log(f"    {body['verification_uri_complete']}")
    log("")
    log(f"  code {body['user_code']} - expires in {body['expires_in'] // 60} minutes")
    log("")

    interval = body.get("interval", 5)
    deadline = time.time() + body.get("expires_in", 300)
    while time.time() < deadline:
        time.sleep(interval)
        status, tok = _post(
            "/token",
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": body["device_code"],
                "client_id": client_id(),
            },
        )
        if status == 200 and tok.get("id_token"):
            log("  Authenticated.")
            return tok
        err = tok.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        sys.exit(f"toolbox: device flow failed: {tok}")

    sys.exit("toolbox: timed out waiting for approval")


def get_token(force_login=False, interactive=True):
    """A valid Dex id_token: from cache, by silent refresh, or by browser login.

    With interactive=False, returns None rather than starting a browser login.
    The proxy uses that: a device-flow prompt printed from a background process
    while the CLI hangs is bewildering, and concurrent requests would each start
    their own flow. Interactive login belongs in `toolbox-login`.
    """
    cache = {} if force_login else _read_cache()

    if _valid(cache.get("id_token")):
        return cache["id_token"]

    tok = None
    if not force_login and cache.get("refresh_token"):
        tok = _refresh(cache["refresh_token"], quiet=not interactive)
    if tok is None:
        if not interactive:
            return None
        tok = _device_flow()

    # Dex does not always return a new refresh token on refresh; keep the old one.
    if not tok.get("refresh_token") and cache.get("refresh_token"):
        tok["refresh_token"] = cache["refresh_token"]

    _write_cache(tok)
    return tok["id_token"]


# ---------------------------------------------------------------------------
# OpenBao
# ---------------------------------------------------------------------------
# OpenBao needs its own token; the Dex token only gets us past the edge. Exchange
# one for the other so a single `toolbox-login` leaves both CLIs usable.
#
# This posts to the login endpoint directly rather than using `bao login`: the
# OpenBao CLI registers no `jwt` auth method (only `oidc`, which is the browser
# redirect flow), so `-method=jwt` fails with "Unknown auth method".


def bao_roles():
    return [
        r.strip()
        for r in _env("TOOLBOX_BAO_ROLES", "editor-jwt,reader-jwt").split(",")
        if r.strip()
    ]


def bao_addr():
    return _env("BAO_ADDR", "http://127.0.0.1:8200")


def bao_token_path():
    return os.path.expanduser(_env("BAO_TOKEN_PATH", "~/.vault-token"))


def bao_login(id_token):
    """Exchange the Dex token for an OpenBao token. Returns the role used, or None.

    Roles are tried most-privileged first; the role's bound_claims decide which
    one a given user is actually entitled to, so a rejection here is expected and
    not an error.
    """
    last = None
    for role in bao_roles():
        body = json.dumps({"role": role, "jwt": id_token}).encode()
        req = urllib.request.Request(
            bao_addr() + "/v1/auth/oidc/login", data=body, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except urllib.error.HTTPError as e:
            last = e.read().decode(errors="replace")[:200]
            continue
        except urllib.error.URLError as e:
            log(f"toolbox: cannot reach OpenBao at {bao_addr()}: {e.reason}")
            return None

        tok = (data.get("auth") or {}).get("client_token")
        if tok:
            p = bao_token_path()
            os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
            with open(p, "w") as f:
                f.write(tok)
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
            return role

    if last:
        log(f"toolbox: OpenBao login failed for {bao_roles()}: {last}")
    return None
