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

**Falta el deploy real, y se está haciendo en otra sesión.**
`.github/workflows/deploy.yml` está escrito —imágenes a GHCR, deploy por
SSH, `alembic upgrade head`, comprobación de salud y rollback al tag
anterior— pero **sin estrenar**: la VM de Oracle, el dominio y el cliente
OAuth de Google no existían al escribir esto. Su paso de comprobación previa
falla con un mensaje claro mientras falten los secretos, en vez de dejar un
deploy a medias.

La provisión es trabajo manual sobre consolas externas (Oracle Cloud, DNS,
Google Cloud, Settings de GitHub), no cambios en este repositorio: la lista
está en `docs/deployment.md`. Se acordó el 2026-09-03 sacarla a su propia
sesión, en paralelo, precisamente porque **no bloquea nada de código**.

Cuando ese deploy corra en verde, lo único que cambia aquí es este bloque:
M0 queda cerrado y no hay que retocar código.

## Siguiente objetivo principal: Fase 1 — el núcleo de la aplicación

Según `ARCHITECTURE.md` §14, Fase 1 es exactamente esto y nada más: pegar
texto de una oferta → clasificar con LLM → scoring → recomendar variante →
descargar el PDF que CI ya construyó. Seguimiento, Telegram y más canales de
ingesta son las Fases 3 y 4, no esta.

La Fase 0 (esqueleto) que `ARCHITECTURE.md` pone antes de la Fase 1 no
existía en este repositorio: se absorbió como M0, la primera rebanada.

Troceo acordado con Pablo el 2026-09-03: cuatro rebanadas verticales, cada
una funcionando de punta a punta.

- **M0 — Esqueleto desplegado.** Código hecho y verificado en local (ver
  arriba). Solo queda estrenar el deploy, que depende de provisionar
  infraestructura a mano y va por su propia sesión. **No bloquea M1.**
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
- Las rebanadas de código (M1 → M3) van en serie: cada una construye sobre
  la anterior. La provisión de infraestructura de M0 es lo único que corre
  en paralelo, porque no toca código.
- `api` y `web` son componentes nuevos: su harness (lint, tipos, tests) se
  configura como parte de su bootstrap, no después — regla de `AGENTS.md`.
- Al cerrar cada rebanada, actualizar este archivo con el estado comprobado y
  ampliar `docs/decisions/fase-1-*.md` con qué se integró y por qué.

## Siguiente paso: M1 — ingesta + extracción

Es el objetivo de la próxima sesión de desarrollo, y **no espera al deploy**:
se trabaja contra el Compose local, igual que M0.

### Alcance

`POST /api/offers/ingest` recibiendo **solo texto pegado** —el canal más
simple de los cinco; los demás son Fase 4— y produciendo, con el LLM, las
capas `capture` y `extraction` de `Futuro/docs/OFFER_DATA_CONTRACT.md`. Más
la pantalla "Oferta" mínima que las enseñe.

Fuera de M1, aunque se toque de refilón: el scoring y la recomendación de
variante son M2, y la entrega del PDF es M3.

### Lo que el contrato exige y el código tiene que hacer cumplir

Estas no son preferencias, son reglas cerradas en el contrato. El patrón es
el mismo que en `cv_builder`: **el LLM elige y cita, el código valida.**

- Cada campo de `extraction` lleva `evidence`: `published` obliga a
  `source_quote`, `inferred` obliga a `reasoning` y `confidence`, `absent`
  no se rellena nunca con una estimación.
- Un requisito no puede marcarse `meets` sin `evidence_ref` a
  `profile/evidence_bank.md` o al banco de bullets. Sin referencia, el
  máximo es `partial`.
- `posting_status` no vale `active_verified` sin `status_checked_at`.
- Empresa que publica y empleador final son dos referencias distintas
  (`posting_company_id`, `employer_company_id` + `employer_confidence`),
  nunca un solo campo.
- `capture` es inmutable, con `raw_text_sha256` para detectar reingestas.
  `extraction` es inmutable y versionada por `prompt_version`: reextraer
  crea fila nueva, no sobrescribe.
- Los vocabularios cerrados (`role_family`, `seniority_label`, `work_mode`,
  `contract_vehicle`, `posting_status`) salen de `config/objectives.yaml` y
  del propio contrato.

### Lo que M1 arrastra consigo

- Las primeras tablas y por tanto la primera migración de Alembic, que en M0
  quedó montado a propósito sin ninguna.
- `redis` y `worker` en el compose: las llamadas al LLM son el primer
  trabajo que justifica la cola.
- El servicio de Postgres en el job de tests de la API del CI, que M0 dejó
  fuera porque sus tests no lo necesitaban.
- El módulo de LLM aislado con structured outputs (`ARCHITECTURE.md` §2), y
  el registro de coste por ejecución.
