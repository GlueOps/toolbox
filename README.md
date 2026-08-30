# GlueOps Toolbox

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
| `toolbox-login --force` | Re-authenticate, e.g. to switch accounts. |
| `toolbox-token` | Print the raw token, for scripting. |

## Configuration

| Variable | Default | |
|---|---|---|
| `TOOLBOX_CAPTAIN_DOMAIN` | — | **Required.** e.g. `nonprod.example.onglueops.rocks` |
| `TOOLBOX_CLIENT_ID` | `toolbox` | Dex client used to mint the token |
| `TOOLBOX_DEX_URL` | `https://dex.$DOMAIN` | |
| `TOOLBOX_BAO_UPSTREAM` | `https://vault.$DOMAIN` | |
| `ARGOCD_SERVER` | `argocd.$DOMAIN` | |
| `TOOLBOX_PROXY_PORT` | `8200` | Loopback port the OpenBao proxy listens on |
| `TOOLBOX_TOKEN_CACHE` | `~/.config/glueops/toolbox-token.json` | |

## How it works

**Getting a token.** `toolbox-login` runs the OIDC **device flow** against Dex.
That matters: there's no loopback listener and no redirect URI, so it works from
inside a container whose browser is on the host — a `localhost:8085` callback
would not. Dex issues a refresh token alongside, so the browser step happens once
rather than daily.

**ArgoCD** accepts that token directly (it's configured with the toolbox audience
in `allowedAudiences`), so one token satisfies both the edge and ArgoCD itself.

It has to be passed as `-H "Authorization: …"`, though — **not** `ARGOCD_AUTH_TOKEN`.
The CLI sends that one in a `Token:` header, which oauth2-proxy doesn't read, so
the edge sees no credential and bounces the request to a login page; the CLI then
fails with the rather unhelpful `rpc error: unexpected EOF`. `-H` is a global flag,
so the wrapper just prepends it and sets the token fresh on every call.

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

The proxy binds to `127.0.0.1` only — it attaches your credential to whatever it
forwards, so it must never be exposed.

## Platforms

Built for `linux/amd64` and `linux/arm64`, so Apple Silicon is native — no
emulation, no Rosetta.

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
