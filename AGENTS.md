# Instructions for AI agents

This container gives you working `argocd` and `bao` against a GlueOps cluster.

## Start here

Run these three commands now, in order. Everything below is reference — read it
only if something fails.

```bash
# 1. start the container (ask the human for the captain domain if you weren't given one)
docker run -d --name toolbox \
  -e TOOLBOX_CAPTAIN_DOMAIN=<captain-domain> \
  -v glueops-toolbox:/home/toolbox/.config/glueops \
  ghcr.io/glueops/toolbox:latest sleep 3600

# 2. start the login and read the URL out
docker exec -d toolbox sh -c 'toolbox-login > /tmp/login.log 2>&1'
sleep 4
docker exec toolbox cat /tmp/login.log
```

**Put that URL and code in your reply immediately.** The human approves in a
browser; they cannot approve what they have not seen. Then wait for it:

```bash
# 3. poll until authenticated, then run whatever you were asked
for _ in $(seq 1 60); do
  docker exec toolbox grep -q 'Authenticated\.' /tmp/login.log && break
  sleep 5
done
docker exec toolbox bash -lc 'argocd app list'
```

## Do not

- **Don't clone this repository.** You don't need it. The image on the registry is
  the whole product; this file is the whole interface.
- **Don't read the source to work out how it functions.** The proxy, the wrappers
  and the login helper are implementation detail. Nothing in them changes what you
  type, and reading them is minutes of work for no answer.
- **Don't probe the environment first** — network egress, Python libraries,
  container internals. If step 1 runs, you're fine; if it doesn't, the error tells
  you what's wrong.
- **Don't use `docker run -it`.** You have no TTY. That is what step 1 avoids.

Get the login URL in front of the human as fast as you can — the code expires five
minutes after it is issued, and every command you run first eats into that.

---

Everything below is reference.

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

If a step in **Start here** fails, this is what each one is doing and why.

**The captain domain** (e.g. `prod.foobar.onglueops.com`) is not in this repo and
cannot be guessed. Ask for it.

**`docker run -it` cannot work** — you have no TTY, so there is nothing to type
into and no way to read the device URL back out. Detached plus `docker exec` is
the whole reason for the shape of step 1.

**`docker exec -d`, not `... &`** — a backgrounded `docker exec` dies with the
shell that started it, and each command you run is usually a fresh shell, so the
login would be killed before anyone could approve it.

**`bash -lc` is required** for every command. `docker exec` bypasses the
ENTRYPOINT, and the CLIs are configured in `/etc/toolbox-env.sh`, which login
shells source. `docker exec toolbox argocd app list` will not work.

**`Already authenticated.`** with no URL means the cached volume still holds a
valid token. Skip to the command. Codes expire after five minutes; if one lapses,
rerun `toolbox-login` and show the new URL.

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
