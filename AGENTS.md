# Instructions for AI agents

This repository builds a container that gives you working `argocd` and `bao`
against a GlueOps cluster. See [README.md](README.md) for what it is and how a
human uses it.

You already know those CLIs. This file is only about getting authenticated, which
is the part you cannot work out from the code. Follow it end to end before running
anything — the whole sequence is here, so nobody should have to explain it to you
in a prompt.

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
  -e TOOLBOX_BAO_ROLES=reader \
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
- **Default to `TOOLBOX_BAO_ROLES=reader`** unless asked to change something. It's
  enforced server-side: writes return `403 permission denied`.
- **Don't mutate anything unasked** — `argocd app sync`, `bao kv put` and friends
  act on live infrastructure.
- **Clean up with `docker rm -f toolbox`,** but leave the volume: it holds the
  login, so the human isn't asked to approve again next time.
