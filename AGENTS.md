# Instructions for AI agents

This repository builds a container that gives you working `argocd` and `bao`
against a GlueOps cluster. See [README.md](README.md) for what it is and how a
human uses it.

This file is only about getting authenticated, which is the part you cannot work
out from the code. Follow it end to end before running anything — the whole
sequence is here, so nobody should have to explain it to you in a prompt.

## The two tools

**`argocd`** — [argoproj/argo-cd](https://github.com/argoproj/argo-cd), GitOps
continuous delivery for Kubernetes. It manages `Application` resources that sync a
cluster to git. The CLI talks to a central API server, not to the Kubernetes API,
so it does not need kubeconfig. Currently `v3.3.12` in this image.

**`bao`** — [openbao/openbao](https://github.com/openbao/openbao), a secrets
manager. It is an open-source fork of HashiCorp Vault, so almost everything you
know about Vault applies: same API shape, same path layout (`secret/`, `sys/`,
`auth/`), same policy model. Two differences that will trip you up:

- The binary is `bao`, not `vault`, and the environment variables are `BAO_*`
  (`BAO_ADDR`, `BAO_TOKEN`). The `VAULT_*` names still work, and `BAO_*` wins if
  both are set — this container sets both, so either will do.
- It has diverged from Vault in places. Don't assume a Vault feature exists; check
  first. For example the CLI registers no `jwt` auth method, so
  `bao login -method=jwt` fails even though the `jwt` auth backend is mounted and
  works over the API.

Currently `2.4.4` in this image. Its docs are at
[openbao.org/docs](https://openbao.org/docs/), and where they are thin the Vault
documentation is usually still correct.

The one thing you can't do is authenticate. Login is a device flow: a human opens
a URL and approves with GitHub. Start it, **give the URL to the person you're
working for**, wait for them, then run whatever you were asked.

**You need the cluster's captain domain**, e.g. `prod.foobar.onglueops.com`.
It is not in this repo and you cannot guess it. If it wasn't given to you, ask for
it before starting — everything below depends on it.

**Run detached, not `docker run -it`.** You have no TTY, so an interactive
container gives you nothing to type into and no way to read the URL back out:

```bash
docker run -d --name toolbox \
  -e TOOLBOX_CAPTAIN_DOMAIN=<captain-domain> \
  -v glueops-toolbox:/home/toolbox/.config/glueops \
  ghcr.io/glueops/toolbox:latest sleep 3600
```

Without a TTY the entrypoint skips its automatic login, which is what you want —
you drive it in the next step.

**Log in in the background and relay the URL.** `toolbox-login` blocks until the
human approves:

```bash
docker exec toolbox toolbox-login > /tmp/login.log 2>&1 &
sleep 4
cat /tmp/login.log
```

Show them the URL and the code, and stop. Don't poll silently — they can't approve
something they haven't been shown. When they confirm, read the log again:
`Authenticated.` means you're through, and a second line reports whether the
OpenBao login also succeeded.

`Already authenticated.` with no URL means the cached volume still holds a valid
token. That's success — carry on. Codes expire after five minutes; if one lapses,
just run `toolbox-login` again.

**Use a login shell for commands.** `docker exec` bypasses the ENTRYPOINT, and the
CLIs are configured in `/etc/toolbox-env.sh`, which login shells source:

```bash
docker exec toolbox bash -lc 'argocd app list'
docker exec toolbox bash -lc 'bao kv list secret/'
```

`docker exec toolbox argocd app list` — without `bash -lc` — will not work.

**Rules.**

- **Never print the token.** `toolbox-token` emits a live credential, and you don't
  need to read it — the wrappers pass it for you.
- **You get OpenBao `editor` by default**, which can create, update and delete
  secrets. That is deliberate, so you can do the work without a second login — but
  it means nothing stops you at the door.
- **So don't mutate anything you weren't asked to.** `bao kv put`, `bao kv delete`,
  `argocd app sync` and friends act on live infrastructure. Read first; change only
  what was actually requested; say what you changed.
- **`TOOLBOX_BAO_ROLES=reader` constrains you** to read and list, enforced
  server-side — writes return `403 permission denied`. Worth setting on the run
  command when you know the task is read-only, so a mistake cannot land.
- **Clean up with `docker rm -f toolbox`,** but leave the volume: it holds the
  login, so the human isn't asked to approve again next time.
