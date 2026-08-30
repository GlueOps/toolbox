# GlueOps Toolbox

> **AI agents:** you have no TTY, so skip the quickstart below. Run this now —
> it is the complete happy path, and you don't need to read anything else first.
> Open [AGENTS.md](AGENTS.md) only if a step fails.
>
> ```bash
> docker run -d --name toolbox -e TOOLBOX_CAPTAIN_DOMAIN=<captain-domain> \
>   -v glueops-toolbox:/home/toolbox/.config/glueops ghcr.io/glueops/toolbox:latest \
> && docker exec toolbox toolbox-login --begin
> ```
>
> Put the URL it prints in your reply, then
> `docker exec toolbox toolbox-login --wait && docker exec toolbox bash -lc 'argocd app list'`.
> Every later command is `docker exec toolbox bash -lc '...'`.

The platform CLIs in one container, already wired up to authenticate. Developers
don't install `argocd`, `bao`, or anything else locally — and they don't need
`kubectl` or cluster access.

```bash
docker run -it --rm \
  -e TOOLBOX_CAPTAIN_DOMAIN=<your-captain-domain> \
  -v glueops-toolbox:/home/toolbox/.config/glueops \
  ghcr.io/glueops/toolbox:latest
```

You'll be given a URL to open and approve with GitHub. After that:

```bash
argocd app list
bao kv get secret/my-app
```

No flags, no `argocd login`, no `bao login`. Both CLIs behave normally.

> Mount the named volume. Without it the login is thrown away when the container
> exits and you re-authenticate every run.

## Why a container

Everything on a GlueOps cluster sits behind oauth2-proxy, which expects a browser
session cookie. CLIs don't have one, so out of the box every request is answered
with a login redirect. Getting past that needs a token, and — for OpenBao — a
header on every single invocation that no shell wrapper can place reliably.

The container handles all of it, so the CLIs are just the CLIs.

## Commands

| | |
|---|---|
| `argocd …` | ArgoCD CLI. Authenticated per-invocation, so a long shell never goes stale. |
| `bao …` | OpenBao CLI, pointed at a local proxy that attaches your token. |
| `toolbox-login` | Authenticate. Runs automatically on an interactive start. |
| `toolbox-login --begin` / `--wait` | The same login in two halves: print the URL and return, then block until approved. For callers that can't sit on a blocking command. |
| `toolbox-login --force` | Re-authenticate, e.g. to switch accounts. |
| `toolbox-token` | Print the raw token, for scripting. |


## Configuration

| Variable | Default | |
|---|---|---|
| `TOOLBOX_CAPTAIN_DOMAIN` | — | **Required.** e.g. `prod.foobar.onglueops.com` |
| `TOOLBOX_CLIENT_ID` | `toolbox` | Dex client used to mint the token |
| `TOOLBOX_DEX_URL` | `https://dex.$DOMAIN` | |
| `TOOLBOX_BAO_UPSTREAM` | `https://vault.$DOMAIN` | |
| `ARGOCD_SERVER` | `argocd.$DOMAIN` | |
| `TOOLBOX_PROXY_PORT` | `8200` | Loopback port the OpenBao proxy listens on |
| `TOOLBOX_TOKEN_CACHE` | `~/.config/glueops/toolbox-token.json` | |
| `TOOLBOX_EXTRA_CA` | — | Path to a mounted CA certificate to trust, for networks that terminate TLS at an egress proxy. Appended to the system store, so public CAs keep working. |
| `TOOLBOX_BAO_ROLES` | `editor,reader` | OpenBao roles tried at login, in order |
| `TOOLBOX_BAO_AUTH_PATH` | `jwt` | OpenBao auth mount the CLI logs in through |

## How it works

**Getting a token.** `toolbox-login` runs the OIDC **device flow** against Dex.
That matters: there's no loopback listener and no redirect URI, so it works from
inside a container whose browser is on the host — a `localhost:8085` callback
would not. Dex issues a refresh token alongside, so the browser step happens once
rather than daily.

**ArgoCD** accepts that token directly (it's configured with the toolbox audience
in `allowedAudiences`), so one token satisfies both the edge and ArgoCD itself.

It needs to go in **two** headers, because each side reads only its own:

| | header | read by |
|---|---|---|
| `ARGOCD_AUTH_TOKEN` | `Token: <jwt>` | ArgoCD |
| `-H "Authorization: …"` | `Authorization: Bearer <jwt>` | oauth2-proxy |

Send only the env var and the edge sees no credential, redirects to a login page,
and the CLI reports `rpc error: unexpected EOF`. Send only `-H` and you get past
the edge with `Token:` empty, so ArgoCD answers `Unauthenticated: no session
information`. The wrapper sets both, fresh on every call.

**OpenBao** can't work that way. Its own credential travels in `X-Vault-Token`,
and the edge needs an `Authorization` bearer as well. `bao` has a `-header` flag,
but it must sit after the subcommand and before any positional argument —

```
bao kv get -header="…" secret/foo     ✓
bao kv get secret/foo -header="…"     ✗   flags must precede positional arguments
bao -header="…" kv get secret/foo     ✗   no global flag position
```

— and since `bao kv list secret` is indistinguishable from a subcommand plus a
path, no wrapper can place it correctly in general. So instead the container runs
a small loopback proxy that adds the header and forwards upstream, and points
`BAO_ADDR` at it. `bao` then needs no flags at all and scripts work unmodified.

`toolbox-login` also exchanges your Dex token for an OpenBao token, so `bao` is
usable immediately. It posts to the login endpoint directly rather than running
`bao login -method=jwt`, because the OpenBao CLI registers no `jwt` method — only
`oidc`, which is the browser redirect flow. Roles are tried most-privileged first
(`TOOLBOX_BAO_ROLES`, default `editor,reader`); which one you actually get is
decided by the role's `bound_claims`.

Set `TOOLBOX_BAO_ROLES=reader` to deliberately hold only read access for a
session. The CLI roles live on their own `auth/jwt` mount, separate from the web
UI's `auth/oidc`, which is why they can share the names of the policies they
grant.

The proxy binds to `127.0.0.1` only — it attaches your credential to whatever it
forwards, so it must never be exposed.

## Platforms

Built for `linux/amd64` and `linux/arm64`, so Apple Silicon is native — no
emulation, no Rosetta.

## Releases

Tagged with [release-please](https://github.com/googleapis/release-please) from
conventional commits on `main`. A release tag publishes
`ghcr.io/glueops/toolbox:<version>`, `:<major>.<minor>` and `:latest`, all
multi-arch. Pin a version in anything automated; `:latest` is fine for people.

## Building

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t toolbox .
```

`TARGETARCH` comes from BuildKit and has no default on purpose: a default would
silently put amd64 binaries in an arm64 image when built natively on a Mac.

## Cluster prerequisites

The platform must have a public Dex client matching `TOOLBOX_CLIENT_ID`, that
audience accepted by oauth2-proxy (`oidc_extra_audiences`) and by ArgoCD
(`allowedAudiences`), and jwt-type roles in OpenBao bound to it.
