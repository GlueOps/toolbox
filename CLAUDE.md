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
`docker exec toolbox bash -lc '...'`. Everything else — what fails and why, the
command reference, the rules — is in [AGENTS.md](AGENTS.md). Read it only if a
step fails.
