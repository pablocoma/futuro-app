# Traspaso a la siguiente sesión

Última actualización: 2026-09-05 (M2 cerrada, estrenada con el modelo real, y al día con el modelo de scoring v2).

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

### Fase 1 · M0 — esqueleto, cerrada el 2026-09-05

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

**Desplegado el 2026-09-05 en `https://futuro-pc.duckdns.org`.** M0 queda
cerrado: era lo único que le faltaba.

Infraestructura, toda provisionada ese día: VM Ampere en Madrid (1 OCPU /
6 GB), VCN con subred pública e internet gateway, puertos 22/80/443 abiertos
en la security list **y** en el `iptables` de la VM, Docker con Compose,
dominio DuckDNS, cliente OAuth de Google, `/opt/futuro/.env` y los cinco
secretos del Environment `production`. Los valores concretos están en
`docs/INFRASTRUCTURE.md` del repositorio privado `Futuro`, nunca aquí.

Comprobado contra producción: certificado de Let's Encrypt válido —el reto
HTTP-01 confirma que el puerto 80 llega—, `/api/health` en `ok` con base de
datos y cola, migraciones aplicadas sobre un Postgres vacío, la API cerrada
por omisión (`401` sin sesión), redirección de HTTP a HTTPS, y el login con
Google funcionando de punta a punta.

`main` quedó protegida ese mismo día: PR obligatorio, los siete checks de
`ci.yml` como obligatorios, historial lineal, sin force-push ni borrado.
`enforce_admins` está **desactivado** a propósito, para poder desbloquear un
despliegue urgente si un check se rompiera por causas ajenas.

El porqué de las decisiones de despliegue —y las cuatro trampas que costaron
tiempo— está en `docs/decisions/fase-1-nucleo.md` y en `docs/deployment.md`.

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

### Fase 1 · M2 — scoring y recomendación de variante, cerrada el 2026-09-04

Funciona de punta a punta sin pedir nada: al terminar la extracción, la
oferta se puntúa sola y se le recomienda una variante de CV. El porqué de
cada decisión está en `docs/decisions/fase-1-nucleo.md`, no aquí.

El principio de esta rebanada es **distinto** del de M1 y conviene tenerlo
presente al tocar el código: en la extracción el LLM elegía y citaba; aquí
**el LLM juzga y el código calcula**.

- **La frontera con el repositorio privado.** `futuro_api/data_repo/` lee
  seis ficheros de `Futuro` (`scoring_model.yaml`, `objectives.yaml`,
  `constraints.yaml`, `cv_variants.yaml`, el banco de bullets y la guía de
  variantes) desde un directorio, `DATA_REPO_PATH`. Hoy lo pone un bind
  mount de solo lectura; en M3 lo pondrá el clon de git y **no cambia una
  línea de arriba**. Falla cerrado: sin él no se puntúa y se dice por qué.
- **El esquema.** Cinco tablas nuevas en la migración `0002`:
  `offer_assessments` con sus hijas `offer_assessment_dimensions`,
  `offer_assessment_gates` y `offer_requirement_matches`, más
  `offer_variant_recommendations`. Las cinco append-only, con el mismo
  trigger de inmutabilidad que las dos capas de M1. Doce tablas en total.
- **El código que calcula.** `assessment/scoring.py` es una función pura:
  media ponderada, renormalización, cobertura, cubo de cartera y nivel de
  esfuerzo. El esquema de salida del modelo no tiene dónde escribir nada de
  eso, así que «el código nunca acepta un `value_score` del modelo» es
  cierto por construcción y no por validación.
- **El cruce de requisitos.** Vive en la capa `assessment` y no en
  `offer_requirements`, que es inmutable: los campos `match`,
  `evidence_ref` y `cv_action` de M1 se quedan en NULL **para siempre**.
  `rules.enforce_match_rule` ya se llama con datos de verdad, y
  `evidence_ref` tiene que **resolver** a un bullet `verified` y divulgable.
- **La cola.** Un segundo tipo de trabajo, `offer_assessment`, con dos
  llamadas al modelo. `job_runs` y `llm_calls` aguantaron sin ganar ninguna
  columna, que es lo que M1 predijo. Lo único que cambió es que las
  consultas de trabajos exigen ahora el tipo.
- **Repuntuar.** `python -m futuro_api.assessment.recompute` recorre la base
  de datos y repuntúa sin llamar al modelo. Idempotente por el `sha256` del
  YAML.
- **La pantalla.** La composición ponderada: ancho = peso, alto = nota,
  hueco rayado para lo no puntuable. Más el número grande, los filtros con
  su cita, y la variante con su motivo.

Verificado en esta máquina el 2026-09-04: `make check` limpio (22 + 294 +
14 tests), `make migrate-check` limpio, `make up` con los seis servicios
sanos y `data_repo: ok`, `make e2e` con los 10 tests en verde incluido el
recorrido entero, el cargador probado contra los dos repositorios —el
sintético y el privado real—, y el repuntuado ejecutado en el contenedor.

Y el CI de `dev` en verde tras subirlo: los siete jobs, incluidos gitleaks,
las migraciones sobre Postgres y el E2E sobre el compose.

**Estrenado con el modelo real el 2026-09-05**, con `gpt-5.6-terra` y el
repositorio privado montado: una oferta inventada extraída y puntuada de
punta a punta, **cero correcciones** en las dos llamadas, $0,071 en total
($0,029 extracción + $0,034 scoring + $0,0075 variante). Ya no queda ninguna
llamada sin estrenar en Fase 1.

Enseñó tres cosas, todas en `docs/decisions/fase-1-nucleo.md`: que el cero
se pintaba como una columna vacía (arreglado), que dos aserciones del E2E
estaban atadas al repositorio sintético (arreglado, ahora pasa contra los
dos), y un cuarto hueco del modelo de scoring.

**Los cuatro huecos están cerrados.** `Futuro` publicó
`config/scoring_model.yaml` **v2** el 2026-09-05 y este repositorio
implementó las tres mitades de código que hacían falta: `very_low` va a
`aspirational`, el orden de los cubos queda confirmado, y la condición de
`cheap` se estrecha para que `full` deje de ser inalcanzable. El renombrado
de `expected_net_savings` a `gross_compensation_vs_baseline` no necesitó
código —los nombres de dimensión son vocabulario libre—, y repuntuada la
misma oferta con v2 esa dimensión sacó un 4 donde antes quedaba sin puntuar.

**Lo que queda abierto de ahí:** repuntuar la misma oferta movió dos
dimensiones cuyas anclas no habían cambiado —una de ellas dos puntos sobre
un peso de 20—. Es variación del modelo. **Fijar `temperature` no vale: se
probó el 2026-09-05 y `gpt-5.6-terra` lo rechaza con un 400**, porque es un
modelo de razonamiento. Queda `seed`, sin probar y sin garantía, o aceptar
la variación y apoyarse en que `recompute.py` sí es idempotente, que es lo
que ya está construido. No hay nada que arreglar en el código: hay una
propiedad del modelo que conviene conocer al leer dos puntuaciones.

**Aviso para cuando se abra el PR de `dev` a `main`:** el CI de M1
(`fbed4ce`) se quedó en rojo por gitleaks, con un falso positivo
`generic-api-key` en `services/web/src/lib/api.test.ts` —casi con seguridad
la cookie inventada `futuro_session=abc`—. No bloquea hoy porque
`gitleaks-action` escanea solo los commits del push y ese commit ya pasó,
pero sigue en el historial y volverá a salir en cualquier escaneo que lo
incluya. Cuando toque, la salida es un `.gitleaks.toml` con una lista de
excepciones **acotada a esa ruta y a ese patrón**, no desactivar la regla:
el primer principio del repositorio es que aquí no entran datos personales,
y ese job es lo único que lo comprueba.

**Dato que hay que llevarse a `Futuro`: M2 multiplica por 2,4 el coste por
oferta**, de ~$0,029 a ~$0,071 observados en la primera llamada real. El
presupuesto de `ARCHITECTURE.md` §13 (~1 €/mes) pasa de dar para ~37 ofertas
al mes a dar para ~15.

Los cuatro huecos de `config/scoring_model.yaml` **están cerrados** en la v2
del 2026-09-05 y su mitad de código implementada aquí; el detalle está en
`docs/decisions/fase-1-nucleo.md`. Lo que sigue abierto de ahí es la
variación del modelo entre llamadas, descrita arriba.

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
- **M2 — Scoring + recomendación de variante. Cerrada** el 2026-09-04 (ver
  arriba).
- **M3 — Entrega del PDF + dossier mínimo.** Lectura de solo lectura del
  repositorio privado para localizar el PDF de la variante; confirmar o
  cambiar variante; descargar; dossier mínimo en Postgres. Sin estados ni
  recordatorios (Fase 3). Con esto, Fase 1 queda cerrada.

### Cómo se trabaja esta fase

- Se desarrolla en este repositorio, en su propia sesión de Claude Code.
- No se escribe nada en el repositorio privado `Futuro` desde aquí: solo se
  lee, y solo cuando haya que consultar contrato o diseño.
- Las rebanadas de código (M1 → M3) van en serie: cada una construye sobre
  la anterior.
- Desde el 2026-09-05 hay producción: `main` está protegida y cada merge
  despliega. Un PR a `main` no es un tramite, es un despliegue.
- `api` y `web` son componentes nuevos: su harness (lint, tipos, tests) se
  configura como parte de su bootstrap, no después — regla de `AGENTS.md`.
- Al cerrar cada rebanada, actualizar este archivo con el estado comprobado y
  ampliar `docs/decisions/fase-1-*.md` con qué se integró y por qué.

## Producción

`https://futuro-pc.duckdns.org`, desde el 2026-09-05. Cada merge a `main`
despliega: imágenes arm64 a GHCR, SSH a la VM, `alembic upgrade head`,
comprobación de salud y rollback al tag anterior si falla.

`/api/health` informa de las cuatro piezas. Hoy responde
`data_repo: not_configured`, que **no es un fallo**: el clon de solo lectura
del repositorio privado es precisamente lo que trae M3.

### Cabos sueltos, ninguno bloqueante

- **Backup sin montar.** `pg_dump` diario cifrado a Oracle Object Storage con
  retención de 30 días, según `ARCHITECTURE.md` §12. Hoy no hay copia de la
  base de datos de producción. Lo que hay ahí es recuperable —ofertas
  reingestables— pero eso deja de ser cierto en cuanto se acumulen
  candidaturas.
- **Aviso por Telegram del deploy**, que menciona `ARCHITECTURE.md` §11:
  fuera hasta la Fase 3, cuando haya bot.
- **`enforce_admins` desactivado** en la protección de `main`. Deliberado
  mientras el proyecto se asienta; activarlo es un `gh api` de una línea.
- **La retención de ~93 EUR** de la tarjeta al pasar la cuenta de Oracle a
  Pay As You Go debe desaparecer sola del extracto. Si a los siete días
  sigue como cargo firme, hay que reclamar.
- **Dos credenciales pasaron por una conversación de Claude Code**: el token
  de DuckDNS y el client secret de Google. Ambas regenerables desde sus
  consolas. Queda como decisión consciente, anotada en `Futuro`.

## Siguiente paso: M3 — entrega del PDF y dossier mínimo

Con esto, Fase 1 queda cerrada. No espera al deploy, igual que M1 y M2.

### Alcance

- **El clon de solo lectura del repositorio privado.** M2 dejó montada la
  frontera (`futuro_api/data_repo/`, con `DATA_REPO_PATH` apuntando a un
  directorio) y el clon es lo único que falta detrás: `git clone` con deploy
  key, volumen en la VM, y una política de refresco. El código que lee no se
  toca, y esa es la razón por la que la frontera se montó antes.
  **Aquí sí hay que tocar `docs/deployment.md`** —la deploy key es una pieza
  a provisionar a mano— así que conviene coordinarlo con la sesión del
  deploy si sigue abierta.
- **Localizar y servir el PDF** de la variante recomendada desde el clon, y
  poder confirmar o cambiar la variante. La confirmación de Pablo es una
  fila **suya** en otra tabla, no un `UPDATE` sobre
  `offer_variant_recommendations`: esa fila dice qué eligió el modelo, y eso
  no cambia porque alguien decida otra cosa.
- **Dossier mínimo en Postgres.** Sin estados ni recordatorios, que son
  Fase 3.

### Lo que M3 hereda ya montado

- La frontera con el repositorio privado y el repo de datos sintético para
  los tests, con `DATA_REPO_HOST_PATH` para apuntar al de verdad.
- El vocabulario de variantes sale del disco: solo es elegible una variante
  que tenga carpeta **y** entrada en `config/cv_variants.yaml`. M3 solo
  tiene que bajar un nivel más, al PDF.
- `DATA_REPO_PATH` **no** es obligatorio con `ENV=production`, y eso es una
  decisión de M2 que M3 tiene que revertir: cuando exista el clon, pasa a la
  lista de obligatorias de `Settings.check_production_requirements`.

### Al cerrar M3

Ampliar `docs/decisions/fase-1-nucleo.md`, reescribir este archivo, y con
ello Fase 1 queda cerrada: la siguiente es la Fase 2 (perfil editable), que
es la primera que **escribe** en el repositorio privado y necesita la
mecánica de `pull --rebase`, diff y confirmación de `ARCHITECTURE.md` §5.
