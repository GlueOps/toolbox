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

**Start the login, show the URL, then wait it out.** `toolbox-login` polls Dex on
its own until the human approves, so you don't need to hand the task back and
wait to be told — surface the URL, then block on the same process and carry on the
moment it succeeds.

```bash
docker exec -d toolbox sh -c 'toolbox-login > /tmp/login.log 2>&1'
sleep 4
docker exec toolbox cat /tmp/login.log   # the URL and code
```

Use `docker exec -d`, not `... &`. Detaching inside the container means the login
survives your shell exiting — a backgrounded `docker exec` dies with the shell that
started it, and each command you run is usually a fresh shell.

**Print the URL in your reply, not only in tool output**, before you start waiting.
They cannot approve a code they have not seen, and if it is buried in a command
trace they will not see it.

Then poll until it completes — the code is good for five minutes:

```bash
for _ in $(seq 1 60); do
  docker exec toolbox grep -q 'Authenticated\.' /tmp/login.log && break
  sleep 5
done
docker exec toolbox cat /tmp/login.log
```

`Authenticated.` means you're through, and a second line reports whether the
OpenBao login also succeeded. Now run whatever you were asked — no second prompt
needed.

`Already authenticated.` with no URL means the cached volume still holds a valid
token — skip straight to the command. Codes expire after five minutes; if one
lapses, run `toolbox-login` again and show the new URL.

**Use a login shell for commands.** `docker exec` bypasses the ENTRYPOINT, and the
CLIs are configured in `/etc/toolbox-env.sh`, which login shells source:

```bash
docker exec toolbox bash -lc 'argocd app list'
docker exec toolbox bash -lc 'bao kv list secret/'
```

`docker exec toolbox argocd app list` — without `bash -lc` — will not work.

## Commands

Everything runs through `docker exec toolbox bash -lc '...'`. Only the part inside
the quotes changes, so the rest of this section shows just that.

Quoting: the wrapper uses single quotes, so use **double** quotes inside. If you
need a pipeline or a script, keep it in one `bash -lc` rather than piping out to
the host, so the container's environment applies throughout.

```bash
docker exec toolbox bash -lc 'argocd app list'
docker exec toolbox bash -lc 'bao kv get -format=json secret/my-app'
```

### Argo CD — reading

| | |
|---|---|
| `argocd app list` | every application, with sync and health |
| `argocd app list -o json` | same, machine-readable — use this to filter or sort |
| `argocd app get <app>` | one application in detail, including its resources |
| `argocd app history <app>` | deployment history, newest first |
| `argocd app diff <app>` | live state vs. desired — exits `1` if there is a diff, `0` if none, `2` on error |
| `argocd app manifests <app>` | rendered manifests |
| `argocd app logs <app>` | logs from the app's pods |
| `argocd cluster list` | connected clusters |
| `argocd proj list` | projects |
| `argocd repo list` | configured repositories |

### Argo CD — changing (only when asked)

| | |
|---|---|
| `argocd app sync <app>` | deploy desired state to the cluster |
| `argocd app rollback <app> <id>` | roll back to a history entry |
| `argocd app delete <app>` | remove the application |

### OpenBao — reading

| | |
|---|---|
| `bao kv list secret/` | keys at a path — trailing slash matters |
| `bao kv get secret/<path>` | one secret |
| `bao kv get -format=json secret/<path>` | machine-readable |
| `bao kv get -field=<key> secret/<path>` | one value, unquoted, no trailing newline |
| `bao kv metadata get secret/<path>` | versions and timestamps, no values |
| `bao token lookup` | who you are, which policies you hold |
| `bao token capabilities secret/<path>` | what you may do at a path — check before assuming |
| `bao secrets list` | mounted secrets engines |
| `bao policy read <name>` | a policy's rules |

### OpenBao — changing (only when asked)

| | |
|---|---|
| `bao kv put secret/<path> k=v` | write, creating a new version |
| `bao kv patch secret/<path> k=v` | update one key, leaving others |
| `bao kv delete secret/<path>` | soft-delete the latest version |
| `bao kv destroy -versions=<n> secret/<path>` | permanently remove a version |

`bao kv put` replaces the whole secret — keys you don't pass are dropped from the
new version. Use `patch` to change one field, or read the secret first.

### Checking before you act

```bash
docker exec toolbox bash -lc 'bao token capabilities secret/my-app'
docker exec toolbox bash -lc 'argocd app diff my-app'
```

`token capabilities` tells you what you may actually do at a path, which beats
discovering it from a 403. `app diff` shows what a sync would change. Mind its exit
codes: `1` means a diff was found and `2` means the command failed — so treat
non-zero as "check which", not as "there is drift".

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
