# Atajos de desarrollo. Nada se instala en el Mac: todo corre en Compose.
# Las tareas de calidad tienen además su forma local (`make check`), que es
# la que reproduce exactamente lo que hace CI.

.DEFAULT_GOAL := help
.PHONY: help up down logs ps rebuild shell-api shell-web psql migrate \
        check check-api check-web fmt e2e

help: ## Lista los objetivos disponibles
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Levanta la app en local (http://localhost:8080)
	docker compose up --build -d
	@echo "→ http://localhost:8080"

down: ## Para la app y borra los contenedores (los volúmenes se quedan)
	docker compose down

logs: ## Sigue los logs de todos los servicios
	docker compose logs -f

ps: ## Estado de los servicios
	docker compose ps

rebuild: ## Reconstruye las imágenes sin caché
	docker compose build --no-cache

shell-api: ## Shell dentro del contenedor de la API
	docker compose exec api bash

shell-web: ## Shell dentro del contenedor del frontend
	docker compose exec web sh

psql: ## Cliente psql contra el Postgres de local
	docker compose exec postgres psql -U $${POSTGRES_USER:-futuro} -d $${POSTGRES_DB:-futuro}

migrate: ## Aplica las migraciones pendientes
	docker compose exec api alembic upgrade head

check: check-api check-web ## Lint, tipos y tests de los dos servicios

check-api: ## Harness de la API
	cd services/api && uv sync --frozen
	cd services/api && uv run ruff check .
	cd services/api && uv run ruff format --check .
	cd services/api && uv run mypy
	cd services/api && uv run pytest -q

check-web: ## Harness del frontend
	cd services/web && npm ci
	cd services/web && npm run lint
	cd services/web && npm run typecheck
	cd services/web && npm run test

fmt: ## Formatea el código de la API
	cd services/api && uv run ruff check --fix .
	cd services/api && uv run ruff format .

e2e: ## Smoke test de extremo a extremo contra el compose levantado
	cd e2e && npm ci && npm test
