# GlueOps toolbox - the platform CLIs, preconfigured to authenticate through the
# oauth2-proxy edge. Developers run this instead of installing anything locally.
FROM debian:12-slim

ARG ARGOCD_VERSION=v3.3.12
ARG OPENBAO_VERSION=2.4.4

# Supplied automatically by BuildKit for the platform being built. Deliberately
# left without a default: a default would silently produce an arm64 image full of
# amd64 binaries when someone builds natively on an Apple Silicon Mac.
ARG TARGETARCH

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl python3 jq less git bash \
 && rm -rf /var/lib/apt/lists/*

# argocd is installed as argocd.real; bin/argocd wraps it to attach the edge token.
RUN set -eux; \
    : "${TARGETARCH:?BuildKit must supply TARGETARCH - build with docker buildx}"; \
    curl -fsSL -o /usr/local/bin/argocd.real \
      "https://github.com/argoproj/argo-cd/releases/download/${ARGOCD_VERSION}/argocd-linux-${TARGETARCH}"; \
    chmod +x /usr/local/bin/argocd.real; \
    /usr/local/bin/argocd.real version --client >/dev/null

# OpenBao names its tarballs by uname -m (x86_64), not by Docker's TARGETARCH (amd64).
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) BAO_ARCH=x86_64 ;; \
      arm64) BAO_ARCH=arm64 ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/bao.tar.gz \
      "https://github.com/openbao/openbao/releases/download/v${OPENBAO_VERSION}/bao_${OPENBAO_VERSION}_Linux_${BAO_ARCH}.tar.gz"; \
    tar -xzf /tmp/bao.tar.gz -C /usr/local/bin bao; \
    chmod +x /usr/local/bin/bao; \
    rm -f /tmp/bao.tar.gz; \
    /usr/local/bin/bao version >/dev/null

COPY lib/ /opt/toolbox/lib/
COPY bin/ /usr/local/bin/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/toolbox-token /usr/local/bin/toolbox-proxy \
             /usr/local/bin/toolbox-login /usr/local/bin/argocd \
             /usr/local/bin/entrypoint.sh

# Unprivileged, with the token-cache directory created up front and owned by the
# runtime user - otherwise a mounted volume lands root-owned and the cache write
# fails. Deliberately no VOLUME directive: it would create a fresh anonymous
# volume on every `docker run`, so the cache would never survive a restart and
# developers would re-authenticate every time. Persistence is opt-in, by mounting
# a named volume over this path (see README).
RUN useradd -m -u 1000 -s /bin/bash toolbox \
 && mkdir -p /home/toolbox/.config/glueops \
 && chown -R toolbox:toolbox /home/toolbox
USER toolbox
WORKDIR /home/toolbox

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
