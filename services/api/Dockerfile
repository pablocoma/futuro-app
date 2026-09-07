# syntax=docker/dockerfile:1
#
# Imagen de la API. Se construye para arm64 tanto en local (Apple Silicon)
# como en producción (Oracle Ampere), así que no hay emulación en ninguno de
# los dos lados.
#
# En fases posteriores el worker de arq comparte esta misma imagen y solo
# cambia el comando, como decide ARCHITECTURE.md §4.
FROM python:3.13-slim

# El binario de uv se copia de su imagen oficial en vez de instalarse con
# pip: es una versión fijada y no arrastra dependencias en la imagen final.
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# `git` y el cliente de SSH: Fase 2 gestiona su propio clon de
# lectura-escritura del repositorio privado desde dentro de la propia app
# (`data_repo_write/git_ops.py`), a diferencia del clon de solo lectura de
# M3, que clona CI y nunca entra en esta imagen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Las dependencias van en una capa propia, antes del código, para que
# editar un módulo no invalide la instalación completa.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY git ./git
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

RUN useradd --create-home --uid 10001 api
USER api

EXPOSE 8000

CMD ["uvicorn", "futuro_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
