#!/usr/bin/env bash
# Bring up the local OpenBao proxy, then hand over to the user's command.
set -euo pipefail

: "${TOOLBOX_CAPTAIN_DOMAIN:?set TOOLBOX_CAPTAIN_DOMAIN, e.g. nonprod.example.onglueops.rocks}"

export ARGOCD_SERVER="${ARGOCD_SERVER:-argocd.${TOOLBOX_CAPTAIN_DOMAIN}}"
# Traefik terminates TLS and argocd-server runs insecure behind it, so the CLI
# has to speak gRPC-web rather than HTTP/2.
export ARGOCD_OPTS="${ARGOCD_OPTS:---grpc-web}"

PROXY_PORT="${TOOLBOX_PROXY_PORT:-8200}"
export BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:${PROXY_PORT}}"
export VAULT_ADDR="$BAO_ADDR"

toolbox-proxy &
for _ in $(seq 1 50); do
    if (exec 3<>/dev/tcp/127.0.0.1/"$PROXY_PORT") 2>/dev/null; then exec 3>&- 3<&-; break; fi
    sleep 0.1
done

# Log in up front when there is a terminal, so the prompt appears here rather than
# from the background proxy midway through someone's first command. Without a tty
# (CI, `docker run` without -it) skip it: the proxy answers 511 with instructions.
if [ -t 0 ]; then
    toolbox-login || true
fi

exec "$@"
