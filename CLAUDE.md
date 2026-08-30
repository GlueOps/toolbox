# CLAUDE.md

Run this now — it is the complete happy path. Ask the human for the captain
domain if you weren't given one:

```bash
./toolbox up <captain-domain>
```

It prints a URL. Write it into your reply — a human approves it in a browser and
the code expires in five minutes — then, in the same turn:

```bash
./toolbox wait && ./toolbox argocd app list
```

If `wait` says `still waiting` (exit 2), run it again. Every later command is
`./toolbox <command>`: `./toolbox bao kv list secret/`, `./toolbox argocd app get x`.

`up` handles the environment itself — starting dockerd, proxies, CAs, host
networking — and prints what it decided. Don't investigate any of that first; if
`up` fails, its last lines say what to check. Everything else is in
[AGENTS.md](AGENTS.md); read it only if a step fails.
