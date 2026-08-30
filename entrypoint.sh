#!/usr/bin/env bash
# Bring up the local OpenBao proxy, then hand over to the user's command.
set -euo pipefail

: "${TOOLBOX_CAPTAIN_DOMAIN:?set TOOLBOX_CAPTAIN_DOMAIN, e.g. prod.foobar.onglueops.com}"

# shellcheck source=/dev/null
. /etc/toolbox-env.sh

PROXY_PORT="${TOOLBOX_PROXY_PORT:-8200}"

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

# `docker run -d` with no command: stay up so the caller can `docker exec` into
# us, instead of bash exiting immediately for want of a terminal. Agents rely on
# this - it is what lets step 1 of AGENTS.md be a bare `docker run -d`.
if [ ! -t 0 ] && [ "$*" = "bash" ]; then
    exec sleep infinity
fi

exec "$@"
