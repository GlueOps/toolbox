# CLAUDE.md

You have no TTY. Run this now — it is the complete happy path; ask the human for
the captain domain if you weren't given one:

```bash
docker run -d --name toolbox -e TOOLBOX_CAPTAIN_DOMAIN=<captain-domain> \
  -v glueops-toolbox:/home/toolbox/.config/glueops ghcr.io/glueops/toolbox:latest &&
docker exec toolbox toolbox-login --begin
```

Write the URL it prints into your reply — a human approves it in a browser and
the code expires in five minutes — then, in the same turn:

```bash
docker exec toolbox toolbox-login --wait && docker exec toolbox bash -lc 'argocd app list'
```

If `--wait` says `still waiting` (exit 2), run it again. Every later command is
`docker exec toolbox bash -lc '...'`.

Two environment fixes, so you don't have to investigate: if docker isn't running,
`docker info >/dev/null 2>&1 || (nohup dockerd >/tmp/dockerd.log 2>&1 & sleep 4)`.
If your sandbox routes egress through a proxy on the host's loopback, start
`dockerd` with `HTTPS_PROXY="$HTTPS_PROXY"` and add
`--network host -e HTTPS_PROXY -e HTTP_PROXY -e NO_PROXY=127.0.0.1,localhost`
(plus `-v /path/to/proxy-ca.crt:/ca.crt:ro -e TOOLBOX_EXTRA_CA=/ca.crt` if that
proxy intercepts TLS) to
the `docker run` above.

Everything else — what fails and why, the command reference, the rules — is in
[AGENTS.md](AGENTS.md). Read it only if a step fails.
