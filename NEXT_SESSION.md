# Traspaso a la siguiente sesión

Última actualización: 2026-09-03.

Este archivo contiene el estado operativo del proyecto. Las reglas duraderas
están en `AGENTS.md`; no deben duplicarse aquí.

## Estado comprobado

- Repositorio creado el 2026-09-02 como público bajo la cuenta `pablocoma`.
  Bootstrap: `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore` y el harness
  de Claude Code. `dev` existe desde el commit fundacional; el trabajo se
  hace ahí.
- Las decisiones de arquitectura están cerradas en `ARCHITECTURE.md` del
  repositorio privado `Futuro`, no duplicadas aquí. El contrato de datos de
  una oferta (`docs/OFFER_DATA_CONTRACT.md`) y el diseño de pantallas
  (`docs/APP_SCREENS.md`) también están cerrados ahí.

### Fase 0.5 — cerrada el 2026-09-03

La mitad de este repositorio: `pyproject.toml`/`uv.lock` (Python 3.13 vía
`uv`), el paquete `src/cv_builder/` (modelos, `claim_rules`, `build`,
`render`, `cli` — uso y contrato de la plantilla del maestro en
`src/cv_builder/README.md`), 22 tests contra fixtures sintéticas propias en
`tests/`, y `docker/Dockerfile` (Tectonic 0.17.0 con caché precalentada).
Verificado en esta máquina: `uv sync`, `ruff`, `mypy --strict`, `pytest`
(22 passed), `docker build` y un smoke test completo dentro del contenedor.

La mitad del repositorio privado también está cerrada: el maestro real
convertido a plantilla Jinja2, el workflow `Futuro/.github/workflows/build-cvs.yml`
—que consume el paquete `cv_builder` de este repositorio— corrió con éxito en
GitHub Actions, y las cinco variantes reales están regeneradas con su PDF. El
pipeline de CVs no requiere más trabajo; **no hay que tocarlo**.

Único pendiente menor, anotado del lado de `Futuro` y no bloqueante: ese
workflow referencia `futuro-app` en `ref: dev`, una rama mutable. Cuando este
repositorio tenga tags o un `main` estable, conviene fijar una referencia
concreta.

El porqué de cada decisión de implementación de esta mitad está en
`docs/decisions/fase-0.5-workflow-de-cvs.md`, no aquí.

### Fase 1 · M0 — esqueleto, construido y verificado en local

Componentes nuevos, cada uno con su harness desde su primer commit:

- `services/api/` — FastAPI + uv (Python 3.13). `GET /api/health` (público,
  503 con cuerpo cuando Postgres no contesta), OAuth de Google con
  `Authlib`, cookie de sesión firmada y allowlist revalidada en cada
  petición. La API está cerrada por omisión: un middleware deniega todo lo
  que no esté en la lista de rutas públicas. Alembic montado sin migraciones
  todavía. 14 tests.
- `services/web/` — Next.js 16 (App Router) + Tailwind v4, paleta "Plano
  técnico" de `docs/APP_SCREENS.md`. Una página, renderizada en servidor,
  que pinta el estado de los cuatro servicios y de la sesión. 5 tests.
- `docker-compose.yml` + `docker-compose.override.yml` — `caddy`, `api`,
  `web`, `postgres`. Producción y local comparten definición; el override
  añade bind mounts, recarga en caliente y los puertos expuestos. `redis` y
  `worker` no entran hasta que haya llamadas al LLM (M1).
- `caddy/Caddyfile` — un solo origen para frontend y API, así que no hay
  CORS y la cookie es de primera parte.
- `e2e/` — smoke test de Playwright contra el Compose levantado. 3 tests.
- `.github/workflows/ci.yml` — en `dev`: `gitleaks`, harness de
  `cv_builder`, de `api` y de `web`, E2E sobre el compose, y build de las
  dos imágenes en runner arm64 nativo.
- `Makefile`, `.env.example`, `docs/deployment.md`.

Verificado en esta máquina el 2026-09-03: `make check` limpio (22 + 14 + 5
tests), `docker compose up --build` con los cuatro servicios sanos,
`/api/health` y la página correctos a través de Caddy en el puerto 8080,
camino degradado con `postgres` parado, `alembic upgrade head` como no-op
válido, y los 3 tests E2E en verde. El detalle de qué se decidió y por qué
está en `docs/decisions/fase-1-nucleo.md`.

**Lo que falta para cerrar M0, y no se puede hacer desde aquí:** el deploy
real. `.github/workflows/deploy.yml` está escrito —imágenes a GHCR, deploy
por SSH, `alembic upgrade head`, comprobación de salud y rollback al tag
anterior— pero sin estrenar, porque no existen todavía la VM de Oracle, el
dominio ni el cliente OAuth de Google. Su paso de comprobación previa falla
con un mensaje claro mientras falten los secretos, en vez de dejar un deploy
a medias. La lista de provisión está en `docs/deployment.md`: VM Ampere con
`ufw`, dominio (propio o DuckDNS), cliente OAuth, `.env` de producción en
`/opt/futuro/` y cinco secretos en el Environment `production` de GitHub.

## Siguiente objetivo principal: Fase 1 — el núcleo de la aplicación

Según `ARCHITECTURE.md` §14, Fase 1 es exactamente esto y nada más: pegar
texto de una oferta → clasificar con LLM → scoring → recomendar variante →
descargar el PDF que CI ya construyó. Seguimiento, Telegram y más canales de
ingesta son las Fases 3 y 4, no esta.

**La Fase 0 (esqueleto) no existe todavía en este repositorio.** Solo hay
`cv_builder`: no hay `docker-compose.yml`, ni FastAPI, ni Next.js, ni CI de
aplicación. `ARCHITECTURE.md` pone la Fase 0 antes que la Fase 1 a propósito
("sin esto, todo lo demás se desarrolla a ciegas"), así que el trabajo empieza
por un esqueleto mínimo, no por la lógica de negocio.

Troceo acordado con Pablo el 2026-09-03: cuatro rebanadas verticales, cada
una funcionando de punta a punta.

- **M0 — Esqueleto desplegado.** Código completo y verificado en local (ver
  arriba). Queda solo el deploy real, que depende de provisionar la
  infraestructura a mano.
- **M1 — Ingesta + extracción, sin scoring ni variante.** `POST
  /api/offers/ingest` solo con texto pegado, el canal más simple. El LLM
  produce las capas `capture` + `extraction` de
  `Futuro/docs/OFFER_DATA_CONTRACT.md`, con cita obligatoria por nota.
  Pantalla "Oferta" mínima.
- **M2 — Scoring + recomendación de variante.** Capa `assessment` contra
  `Futuro/config/scoring_model.yaml`; el LLM compara la oferta contra
  `Futuro/cv/variants/README.md` y devuelve variante + confianza + motivo.
  La aritmética la calcula el código, nunca el modelo.
- **M3 — Entrega del PDF + dossier mínimo.** Lectura de solo lectura del
  repositorio privado para localizar el PDF de la variante; confirmar o
  cambiar variante; descargar; dossier mínimo en Postgres. Sin estados ni
  recordatorios (Fase 3). Con esto, Fase 1 queda cerrada.

### Cómo se trabaja esta fase

- Se desarrolla en este repositorio, en su propia sesión de Claude Code.
- No se escribe nada en el repositorio privado `Futuro` desde aquí: solo se
  lee, y solo cuando haya que consultar contrato o diseño.
- `api` y `web` son componentes nuevos: su harness (lint, tipos, tests) se
  configura como parte de su bootstrap, no después — regla de `AGENTS.md`.
- Al cerrar cada rebanada, actualizar este archivo con el estado comprobado y
  ampliar `docs/decisions/fase-1-*.md` con qué se integró y por qué.

## Siguiente paso

Dos frentes, independientes entre sí:

1. **Provisionar la infraestructura** siguiendo `docs/deployment.md` y
   estrenar `deploy.yml` con un merge de `dev` a `main`. Cierra M0.
2. **Empezar M1** (ingesta + extracción). Las referencias cerradas son
   `Futuro/docs/OFFER_DATA_CONTRACT.md` —capas `capture` y `extraction`,
   `evidence` obligatorio en cada campo, ninguna nota sin cita, ningún
   `meets` sin `evidence_ref`— y la pantalla "Oferta" de
   `Futuro/docs/APP_SCREENS.md`. Trae consigo las primeras tablas y por
   tanto la primera migración de Alembic, `redis` y `worker` en el compose,
   y el servicio de Postgres en el job de tests de la API del CI.

M1 no depende de que el deploy esté hecho: se desarrolla contra el Compose
local igual que M0.
