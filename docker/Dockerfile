# syntax=docker/dockerfile:1
#
# Imagen del renderer de CVs: genera el .tex de cada variante con el
# generador Python/Jinja2 (cv_builder) y lo compila a PDF con Tectonic.
# La caché de paquetes de Tectonic se precalienta en build compilando
# docker/sample/sample.tex, para que la compilación real de cada variante
# no necesite red.
FROM python:3.13-slim

ARG TECTONIC_VERSION=0.17.0
ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$TARGETARCH" in \
      arm64) \
        TECTONIC_TARGET=aarch64-unknown-linux-musl; \
        TECTONIC_SHA256=b10954a95404f3ab2328d2fa59a5ebab8e657f893fab096f98be8db7c0c979b8 \
        ;; \
      amd64) \
        TECTONIC_TARGET=x86_64-unknown-linux-musl; \
        TECTONIC_SHA256=8533d07f9ccbd7a65824b9e0459041bca34af1eb33daba48f59215593753a3b7 \
        ;; \
      *) \
        echo "arquitectura no soportada: $TARGETARCH" >&2; exit 1 \
        ;; \
    esac; \
    curl -fsSL -o /tmp/tectonic.tar.gz \
      "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${TECTONIC_TARGET}.tar.gz"; \
    echo "${TECTONIC_SHA256}  /tmp/tectonic.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin tectonic; \
    rm /tmp/tectonic.tar.gz

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# Precalienta la caché de paquetes de Tectonic (~/.cache/Tectonic) para que
# la compilación real de una variante, más adelante, sea offline.
COPY docker/sample/sample.tex /tmp/sample/sample.tex
RUN tectonic -o /tmp/sample /tmp/sample/sample.tex && rm -rf /tmp/sample

ENTRYPOINT ["cv-builder"]
CMD ["--help"]
