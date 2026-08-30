# Instructions for AI agents

This container gives you working `argocd` and `bao` against a GlueOps cluster.

## Start here

Two commands. Everything below them is reference — read it only if one fails.

```bash
# 1. start the container and get the login URL
#    (ask the human for the captain domain if you weren't given one)
./toolbox up <captain-domain>
```

That prints a URL. **Write it, and the code, into your message text now**, then
run step 2 in the same turn. The human approves it in a browser; they cannot
approve what they have not seen, and the code expires five minutes after it is
issued. Never fold `up` and `wait` into one command — the human must see the
URL before you start waiting on it. If `up` prints `Already authenticated.`
there is nothing to approve; go straight to step 2.

```bash
# 2. wait for the approval, then run whatever you were asked
./toolbox wait && ./toolbox argocd app list
```

`wait` returns after about 90 seconds if the human hasn't approved yet, so it
fits under your tool's command timeout: exit code 2 and `still waiting` mean run
it again, nothing is wrong. Once approved it logs you into OpenBao too. Every
later command is `./toolbox <command>`.

**`up` owns the environment.** It starts dockerd if it's installed but not
running, pulls the image, passes proxy variables through, mounts the host's CA
bundle so the container trusts what the host trusts, uses host networking when
the proxy is on the host's loopback, and retries with host networking if the
bridge can't reach Dex. It prints each decision on stderr. Don't check docker,
read proxy documentation, look for CA files or test connectivity before running
it — every one of those is a wasted command; `up` already does the right thing
or tells you exactly what it couldn't do.

## If `up` fails

Its last lines say what happened. The cases:

- **`docker is not installed`** / **`cannot connect to the docker daemon`** and
  you are not root — you need docker, or a user that can reach it. Nothing in
  this repo can fix that; tell the human.
- **`dockerd did not come up`** — `cat /tmp/toolbox-dockerd.log`.
- **`could not reach https://dex.<domain>`** after it tried both networks — the
  domain is wrong, or this host has no route to it. Check
  `curl https://dex.<domain>/healthz` from the host; if that fails too, the
  environment can't reach the cluster and no container flag will change that.
- **`the code expired`** or **`login access_denied`** from `wait` — run
  `./toolbox up <domain>` again and show the new URL.
- **Told to log in as someone else** — `./toolbox toolbox-login --begin --force`
  discards the cached identity and mints a fresh URL, then `./toolbox wait`.

## Do not

- **Don't read the source to work out how it functions.** The proxy, the wrappers
  and the login helper are implementation detail. Nothing in them changes what you
  type, and reading them is minutes of work for no answer.
- **Don't probe the environment first** — docker state, proxy variables, CA
  files, network egress, Python libraries. `up` does all of that and prints what
  it found. If it fails, the error tells you what's wrong.
- **Don't run the container by hand** with `docker run -it`. You have no TTY, and
  `up` already made the decisions a bare `docker run` would get wrong.

Get the login URL in front of the human as fast as you can — the code expires five
minutes after it is issued, and every command you run first eats into that. Step 1
is one command for exactly that reason.

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
into and no way to read the device URL back out. `up` runs the container
detached and drives it with `docker exec`, which is why it exists.

**`--begin` and `--wait` are two halves of one login.** `--begin` asks Dex for a
device code, saves it, prints the URL and returns; run it twice and you get the
same URL back, not a second one. `--wait` polls Dex with that code, for about 90
seconds per call (`TOOLBOX_WAIT_SECONDS`), and exits 2 if the human hasn't
approved yet — just call it again. Both are safe to rerun when already logged in.

**`./toolbox <command>` runs it in a login shell** inside the container, which is
what sources `/etc/toolbox-env.sh` and configures the CLIs. If you ever bypass
the wrapper, it has to be `docker exec toolbox bash -lc '...'` — a bare
`docker exec toolbox argocd app list` will not work.

**`Already authenticated.`** with no URL means the cached volume still holds a
valid token. Skip to the command. Codes expire after five minutes; if one lapses,
rerun `toolbox-login --begin`, show the new URL, then `--wait` again.

## Commands

Everything runs as `./toolbox <command>`; the rest of this section shows just
the command. Arguments are passed through intact, so quote as you normally would.
For a pipeline or a script, wrap it: `./toolbox bash -c 'argocd app list -o json | ...'`
so the container's environment applies throughout.

```bash
./toolbox argocd app list
./toolbox bao kv get -format=json secret/my-app
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
./toolbox bao token capabilities secret/my-app
./toolbox argocd app diff my-app
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
- **Clean up with `./toolbox down`**; it keeps the volume, which holds the login,
  so the human isn't asked to approve again next time. (An abandoned container
  stops itself after four hours — `TOOLBOX_IDLE_SECONDS` — but don't rely on
  that.)
