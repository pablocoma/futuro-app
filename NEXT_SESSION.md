# Traspaso a la siguiente sesión

Última actualización: 2026-09-04.

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

### Fase 1 · M1 — ingesta y extracción, cerrada el 2026-09-04

Funciona de punta a punta desde el navegador: pegar un anuncio, verlo
extraerse y ver lo extraído con la evidencia de cada campo. El porqué de
cada decisión está en `docs/decisions/fase-1-nucleo.md`, no aquí.

- **El esquema.** Siete tablas: `companies`, `offer_captures`,
  `offer_extractions`, `offer_requirements`, `offer_anomalies`, `job_runs` y
  `llm_calls`, en la migración `0001`. Las dos capas del contrato son
  inmutables por un trigger `BEFORE UPDATE`, no por convención.
- **El código que valida.** `offers/rules.py`: toda cita se verifica contra
  el texto pegado, las infracciones sin degradación honesta rechazan la
  extracción entera, y lo degradado se guarda en `corrections` y se enseña
  en pantalla. El esquema de salida del modelo no tiene `status_checked_at`
  ni los campos del cruce con el banco de evidencias: lo que el modelo no
  puede saber, no se le pregunta.
- **El módulo de LLM.** `llm/` con el protocolo, la tabla de tarifas fechada
  del 2026-09-03, el cliente de OpenAI y el `stub`. Modelo:
  `gpt-5.6-terra`, unos 0,034 $ por oferta.
- **La cola.** `redis` y `worker` en el compose, con la tarea de arq, el
  registro de coste por llamada y un barrido de trabajos perdidos.
- **Los endpoints y las pantallas.** `POST /api/offers/ingest` (solo texto
  pegado), el listado, el detalle y la reextracción; `/capturar`,
  `/ofertas` y `/ofertas/[id]`.

Verificado en esta máquina el 2026-09-04: `make check` limpio (148 tests de
la API, 10 del frontend), `make migrate-check` limpio, `make up` con los
seis servicios de `ARCHITECTURE.md` §4 sanos por primera vez, y `make e2e`
con los 6 tests de Playwright en verde, incluido el recorrido entero.

**Lo único no verificado, y no se puede desde aquí:** una extracción con el
modelo de verdad. Todo corre con `LLM_PROVIDER=stub`, que es lo que hace el
harness determinista y gratis. La clave de OpenAI está creada y en el `.env`
local, con presupuesto mensual y auto-recharge desactivado; la primera
llamada real la hace Pablo cuando quiera poniendo `LLM_PROVIDER=openai`.

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
- **M1 — Ingesta + extracción, sin scoring ni variante. Cerrada** el
  2026-09-04 (ver arriba).
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

## Siguiente paso: M2 — scoring y recomendación de variante

Según el troceo, M2 es la capa `assessment` del contrato de datos y la
elección de variante de CV. No espera al deploy, igual que M1.

### Alcance

- **Capa `assessment`**, recalculable, contra
  `Futuro/config/scoring_model.yaml`. La propiedad que justifica separarla
  ya está montada: repuntuar el histórico es recorrer la base de datos, no
  volver a pagar la extracción de cada oferta.
- **El LLM juzga y el código calcula.** El modelo pone la nota de cada
  dimensión y la cita que la sostiene; la media ponderada, la
  renormalización, la cobertura, el cubo de cartera y el nivel de esfuerzo
  los calcula el código. Una nota sin cita es inválida y su dimensión queda
  sin puntuar. El código nunca acepta un `value_score` calculado por el
  modelo.
- **Recomendación de variante**: el LLM compara la oferta con
  `Futuro/cv/variants/README.md` y devuelve variante, confianza y motivo.
  No redacta nada: elige entre cinco documentos que ya existen.
- **La pantalla de la oferta gana su composición ponderada**: el ancho de
  cada barra es el peso de la dimensión y el alto es la nota, con un hueco
  rayado para lo que no se pudo puntuar.

### Lo que M2 arrastra consigo

- La lectura de `Futuro/config/scoring_model.yaml` y de
  `Futuro/cv/variants/README.md`, que son los primeros datos del
  repositorio privado que la aplicación necesita. Decidir si eso se
  adelanta aquí o se deja para el clon de M3 es la primera pregunta de la
  rebanada.
- Con ello, los campos `match`, `evidence_ref` y `cv_action` de
  `offer_requirements`, que M1 dejó a NULL a propósito. La regla que impide
  marcar `meets` sin referencia ya está escrita y probada en
  `rules.enforce_match_rule`; solo hay que empezar a llamarla con datos.
- Un segundo tipo de trabajo en la cola, que es lo que justificó que
  `job_runs` y `llm_calls` fueran dos tablas.

### Al cerrar M2

Ampliar `docs/decisions/fase-1-nucleo.md` y reescribir este archivo con el
estado comprobado y M3 como siguiente objetivo.
