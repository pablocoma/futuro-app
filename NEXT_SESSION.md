# Traspaso a la siguiente sesión

Última actualización: 2026-09-08. Fase 1 completa de punta a punta (M0-M3,
desplegada el 2026-09-05). **Fase 2 completa de punta a punta**: shell
mínimo y M0 (`config/objectives.yaml`, 2026-09-06); M1 (`preferences.yaml`,
`constraints.yaml`, 2026-09-07); M2 (el banco de bullets y el contenido de
variantes de rol, 2026-09-07); M3 (`config/cv_variants.yaml` y
`profile/project_catalog.yaml`, la primera rebanada con validación cruzada
de verdad entre ficheros, 2026-09-07); M4 (`config/scoring_model.yaml`, la
más delicada, cierra Fase 2 entera, 2026-09-08) — ver más abajo. **Fase 3 —
pipeline y seguimiento — en curso**, troceada en ocho rebanadas el
2026-09-08; su rebanada 1 (estados de candidatura) ya está cerrada. Ver más
abajo, sección «Fase 3». Siguiente objetivo: rebanada 2 (Pipeline: tabla
densa).

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

### Fase 1 · M3 — entrega del PDF y dossier mínimo, cerrada el 2026-09-05

Con esto la Fase 1 queda completa. Funciona de punta a punta: con una
oferta ya puntuada, ver el PDF de cualquiera de las variantes disponibles,
confirmar una o cambiarla, y que quede su fila propia sin tocar la
recomendación del modelo. El porqué de cada decisión está en
`docs/decisions/fase-1-nucleo.md`, no aquí.

- **El clon de solo lectura.** El job `deploy` de `deploy.yml` clona
  `career-strategy` (el nombre real en GitHub del repositorio que la
  documentación llama `Futuro`) con una deploy key nueva y de solo
  lectura —`DATA_REPO_DEPLOY_KEY`, distinta de `DEPLOY_SSH_KEY`— y la
  copia a `/opt/futuro/data/repo` en la VM por `rsync`. La clave vive y
  muere en el runner: nunca toca la VM. El refresco va enganchado al
  deploy —cada push a `main` o cada `workflow_dispatch`—, no por su cuenta,
  el mismo gesto manual que ya exige `recompute.py` tras un cambio en los
  datos.
- **`DATA_REPO_PATH` pasa a ser obligatorio con `ENV=production`.** Era la
  reversión que M2 ya anticipó. `api` y `worker` montan el mismo
  `/data/repo` de solo lectura desde `docker-compose.yml`.
- **Localizar el PDF.** `data_repo.pdf_path()` busca por extensión
  (`*.pdf`) dentro de la carpeta ya validada de la variante, no por el
  nombre exacto: el repositorio sintético de los tests usa un prefijo y un
  idioma distintos del privado real a propósito, y ese es justo el caso
  que un nombre hardcodeado no habría visto.
- **El dossier mínimo: tabla `applications`.** Se adopta ya el nombre que
  reserva `docs/OFFER_DATA_CONTRACT.md` para la candidatura completa,
  aunque hoy solo tenga `variant`, `cv_sha256` y `confirmed_at`. Cuelga de
  la captura (no de la extracción ni del assessment), append-only con el
  mismo trigger que las demás capas, y con una referencia opcional a la
  recomendación que confirma o descarta.
- **Dos endpoints nuevos** en `offers/router.py`: `GET
  /api/offers/{id}/cv` sirve el PDF de cualquier variante disponible (por
  omisión, la confirmada o si no hay ninguna la recomendada), y `POST
  /api/offers/{id}/dossier` registra una confirmación nueva sin sobrescribir
  la anterior.
- **La pantalla.** La sección pasa a llamarse «Variante de CV»: enseña la
  recomendación, la confirmación vigente si la hay, y una fila por variante
  disponible con su enlace de descarga y su botón de confirmar —sin
  JavaScript propio, mismo patrón que el botón de puntuar—.

Verificado en esta máquina el 2026-09-05: `make check` limpio (22 + 316 +
17 tests), `make migrate-check` limpio con la migración `0003`, y `make
e2e` con 12 tests en verde —incluidos los dos nuevos de confirmar y
descargar—, corridos contra el repositorio privado **real** montado en
local, no solo el sintético. `data_repo.pdf_path()` además probado a mano
contra ese mismo repositorio real, de solo lectura.

**Desplegado y verificado en producción el mismo 2026-09-05.** La deploy
key de solo lectura y el secreto `DATA_REPO_DEPLOY_KEY` se provisionaron
con `gh` (procedimiento en `docs/deployment.md` §9); el primer deploy real
clonó `main` de `career-strategy` —la rama por omisión del repositorio, un
árbol antiguo sin `cv/` ni `config/`— en vez de `dev`, donde vive el
contenido de verdad, y `/api/health` lo dijo con el motivo exacto
(`data_repo: unreadable`, ficheros ausentes). Se corrigió fijando `--branch
dev` en el `git clone` de `deploy.yml` (detalle en
`docs/decisions/fase-1-nucleo.md`) y se volvió a desplegar: `/api/health`
responde `data_repo: ok` en producción.

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
- **M3 — Entrega del PDF + dossier mínimo. Cerrada** el 2026-09-05 (ver
  arriba). Con esto, **Fase 1 queda cerrada**.

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
`data_repo: not_configured`, que **no era un fallo** hasta ahora: era la
decisión de M2 de no exigirlo. Con M3 ya escrito, `DATA_REPO_PATH` es
obligatorio con `ENV=production`, así que **la API no arrancará** en el
próximo deploy hasta que el clon de solo lectura exista de verdad en la VM
—ver «Fase 1 cerrada» más abajo—.

**Primera oferta real ingerida en producción el 2026-09-05.** La extracción
funcionó de punta a punta con el modelo real: `gpt-5.6-terra`, 3.892 tokens
de entrada (3.341 servidos de caché), 1.989 de salida, 15,3 s y **0,0256 $**.
Es menos de lo que M2 midió en local (~0,029 $) gracias a la caché de
prompt. La puntuación de esa misma oferta falló, y debía fallar, por lo
dicho arriba: sin repositorio de datos no hay modelo de scoring. Con el
clon de M3 desplegado, ese mismo camino debería puntuar.

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

## Fase 1 cerrada, en código y en producción

Las cuatro rebanadas —M0, M1, M2 y M3— están hechas, verificadas en esta
máquina y desplegadas: `/api/health` responde `data_repo: ok` en
`https://futuro-pc.duckdns.org`. El detalle de qué se integró y por qué en
M3 está en `docs/decisions/fase-1-nucleo.md`, no aquí.

La deploy key de solo lectura y el secreto `DATA_REPO_DEPLOY_KEY` ya están
provisionados (procedimiento en `docs/deployment.md` §9). El primer deploy
real clonó `main` de `career-strategy` en vez de `dev` —la rama por
omisión del repositorio no es donde vive el contenido— y quedó corregido
en `deploy.yml`; el detalle está en `docs/decisions/fase-1-nucleo.md`.
Nada pendiente de este lado.

### Hallazgo del 2026-09-06: el diseño construido no seguía el prototipo

Pablo tiene tres artifacts de Claude (2026-08-13) con el diseño de la app:
`Futuro — La arquitectura explicada pieza a pieza`, `Futuro — Prototipo de
interfaz` y `Futuro — Catálogo de opciones`. Comprobado línea a línea contra
lo construido:

- **La paleta sí se seguía bien.** `docs/APP_SCREENS.md` (2026-09-02) ya
  había comparado el catálogo de nueve paletas y elegido "Plano técnico"
  sobre la "Ámbar y pizarra" que usa el prototipo —el prototipo nunca se
  volvió a publicar tras esa decisión, por eso parece distinto—. `globals.css`
  coincide token a token. Confirmado con Pablo que "Plano técnico" es lo
  que quiere: no hay nada que cambiar ahí.
- **La estructura de componentes (botones) y el layout del shell (barra
  lateral, barra inferior) nunca se habían destilado a ningún documento.**
  Cada pantalla de Fase 1 construyó sus botones a su criterio porque no
  había nada escrito con lo que compararlos. Corregido el 2026-09-06:
  - Botones: `.btn-primary` / `.btn-link` en `globals.css`, siguiendo el
    prototipo (relleno sólido + sombra + brillo vs. subrayado que crece),
    aplicados en `page.tsx`. Confirmado con Pablo.
  - Orden acción primaria antes que secundaria (el prototipo siempre pone
    el botón antes que el enlace): corregido en la fila de variante de CV.
  - El shell (barra lateral de 7 pantallas, barra inferior de 4 en móvil
    con Capturar/Oferta invertidos, `⌘K` contextual) quedó documentado en
    `docs/APP_SCREENS.md` §"Estructura del shell", pero **no construido
    todavía**: Fase 1 nunca hizo una barra de navegación persistente, así
    que no hay nada de eso que verificar en un test hoy.
  - Queda sin resolver, y anotado como tal en el propio documento: tres
    convenciones distintas para "marcar un estado" (color puro sin
    ornamento, según el prototipo; subrayado, según la tabla de
    micro-decisiones del mismo documento; símbolo `●`/`▲`/`○` + color,
    según lo construido y `docs/decisions/fase-1-nucleo.md`). No es una
    decisión de estructura, así que no se resolvió aquí; necesita su
    propia conversación con Pablo.

**Decisión sobre el harness de estructura:** no un test de comparación
visual de píxeles —frágil, caro de mantener—, sino aserciones de Playwright
sobre *qué existe y en qué orden*, igual que ya se prueban otras cosas en
este repositorio. Solo se escriben **cuando la estructura ya existe**, no
antes: `e2e/tests/dossier.spec.ts` ya comprueba que la acción primaria de
una fila de variante precede a la secundaria, porque esa fila ya está
construida. La barra lateral y la barra inferior no tienen test todavía
porque no hay shell que probar; en cuanto se construya (Fase 2 o posterior,
no hay milestone asignado todavía), su test entra en el mismo commit que su
código, y debe leer primero `docs/APP_SCREENS.md` §"Estructura del shell"
del repositorio privado.

## Fase 2 — perfil editable (en curso)

Es la primera fase que **escribe** en el repositorio privado `Futuro`
(repositorio de GitHub `career-strategy`), con la mecánica de `pull
--rebase`, `ruamel.yaml`, validación Pydantic, diff en pantalla,
confirmación y `commit`+`push` que describe `ARCHITECTURE.md` §5.
`ARCHITECTURE.md` §14 acota el alcance a **los YAML** del repositorio
privado —no a la prosa en Markdown ni al maestro en LaTeX—.

**Troceo confirmado con Pablo el 2026-09-06**, en cinco rebanadas
verticales, cada una funcionando de punta a punta y **cada una en su propia
sesión de Claude Code**, para no repetir sesiones larguísimas como la que
cerró la Fase 1. Ordenadas de menor a mayor complejidad del YAML que tocan.
Los tamaños de fichero y qué modelos ya existen salen de investigar
`career-strategy` real el 2026-09-06, no de memoria; si algo cambió,
re-investigar antes de dar por buena una cifra de aquí. Sigue siendo
razonable ajustar el troceo si al llegar a una rebanada concreta la
realidad no encaja con lo previsto — no es un contrato inamovible, es la
mejor previsión con la información de hoy.

### Shell mínimo y M0 — cerrados el 2026-09-06

Antes de M0 se construyó el shell mínimo que `NEXT_SESSION.md` había
dejado pendiente de decidir: barra lateral en escritorio y barra inferior
en móvil, con solo las tres entradas que hoy tienen pantalla real
—Pipeline, Capturar, Perfil—; Hoy, Oferta suelta, CVs y Stats quedan fuera
hasta que su fase construya la pantalla detrás. `/` (la portada de M0 de
Fase 1) se queda fuera del shell, accesible por URL directa. El porqué de
cada recorte de alcance está en `docs/decisions/fase-2-perfil-editable.md`.

M0 entrega el mecanismo de escritura completo, demostrado sobre
`config/objectives.yaml`: `futuro_api/data_repo_write/` con `git_ops.py`
(clonar una vez, `pull --rebase`, commitear con autoría `Futuro App
<bot@futuro.local>`, `push`, conflicto sin forzar nada, genérico y
reutilizable por M1-M4) y `objectives.py` (lo único que sabe que ese
fichero existe: carga con `ruamel.yaml` en modo *round-trip*, aplica una
edición, valida contra un modelo Pydantic nuevo, calcula el diff). Dos
endpoints —`POST /api/profile/objectives/diff` y `.../commit`, cada uno
repitiendo pull→carga→aplica→valida desde cero— y la pantalla `/perfil`
dentro del shell, con el formulario, el diff y la confirmación.

El clon de lectura-escritura es **propio de la app**, no el de M3: vive en
`/opt/futuro/data/repo-write` (local: `.dev-data/repo-write`, gestionado
por `make seed-data-repo-write`, enganchado a `make up`, contra un bare
local y no contra GitHub), con una deploy key de lectura-escritura nueva
que **persiste en la VM** —a diferencia de las otras dos, que viven solo
en el runner de un deploy—, porque la app tiene que poder escribir en
cualquier momento futuro. El procedimiento de aprovisionar está en
`docs/deployment.md` §10; **pendiente de que Pablo lo ejecute** antes de
llevar Fase 2 a producción, no bloqueante para seguir con M1 en código.

Dos hallazgos de React/Next.js que costaron tiempo y quedan documentados
en `docs/decisions/fase-2-perfil-editable.md` para no repetirlos en
M1-M4: un fichero `"use server"` solo puede exportar funciones async, y
React resetea los campos **no controlados** de un formulario en cuanto su
`action` termina —hay que usar campos controlados cuando el formulario
tiene que sobrevivir a una acción intermedia, como el paso de "ver diff"
antes de confirmar—.

Verificado en esta máquina el 2026-09-06: `make check` limpio (336 tests
API, 17 web), `make e2e` con los 17 tests en verde incluido el recorrido
nuevo de `perfil.spec.ts`, y el recorrido completo repetido a mano contra
el stack de Compose real —clon en frío, `GET`/`diff`/`commit` por `curl` y
desde el navegador, commit real en el remoto local con la autoría
correcta—. El detalle completo está en
`docs/decisions/fase-2-perfil-editable.md`.

### M1 — `preferences.yaml` y `constraints.yaml`, cerrada el 2026-09-07

Investigado antes de escribir código: los dos ficheros seguían sin tocarse
desde el 2026-08-13 y con el tamaño previsto, pero la forma que el troceo
daba por hecha para `pending_decisions`/`superseded_decisions` era
incorrecta -son una lista plana de strings y un mapa de clave a texto,
respectivamente, no listas de diccionarios-. La complejidad real de "lista
de diccionarios heterogénea" estaba en `disqualifying_conditions`, que el
troceo no había mencionado. El detalle completo, y el porqué de cada
decisión, está en `docs/decisions/fase-2-perfil-editable.md`.

De paso, generalizar el mecanismo a nueve campos de texto plegado más
sacó a la luz un bug latente de M0: reasignar
`primary_objective.statement` en cada escritura, aunque no hubiera
cambiado, podía reflowar su línea con el ancho por omisión de `ruamel` en
vez de con el del fichero real. Corregido con dos funciones nuevas y
compartidas en `data_repo_write/yaml_style.py`
(`set_folded_if_changed`, `set_string_list_if_changed`), que ahora usan
los tres módulos de fichero -`objectives.py` incluido, con su propio test
de regresión-.

Alcance confirmado con Pablo el 2026-09-07, más permisivo que la
recomendación inicial: `hard_constraints` y `superseded_decisions`
totalmente editables (CRUD completo en el segundo caso), y
`disqualifying_conditions` con añadir fila y editar `rule`, sin borrar ni
reordenar. `/perfil` pasa a tener tres pestañas -Objetivos, Preferencias,
Restricciones-, alternadas sin cambiar de URL.

Verificado en esta máquina el 2026-09-07: `make check` limpio (364 tests
API + 17 web), `make e2e` con los 20 tests en verde -incluidos los 3
nuevos de `perfil.spec.ts`-, y el mecanismo comprobado a mano por `curl`
contra el stack de Compose real tras resembrar `.dev-data/` -el remoto de
git local seguía teniendo la forma vieja de los fixtures de M0, y `make
seed-data-repo-write` solo siembra una vez-.

### M2 — el banco de bullets y el contenido de variantes de rol, cerrada el 2026-09-07

Investigado antes de escribir código: los tres ficheros implicados
(`cv/content/professional_bullet_bank.yaml`, 260 líneas, 13 bullets;
`cv/content/role_variant_content.yaml`, 107 líneas, 5 variantes;
`config/cv_variants.yaml`, 179 líneas, de solo lectura en esta rebanada)
seguían sin tocarse desde el 2026-08-13/14 y con la forma exacta prevista.
Lo que **no** se sostuvo fue "reutilizar `src/cv_builder/models.py`":
`cv-builder` y `futuro-api` son dos paquetes Python sin workspace que los
conecte y sin que el `Dockerfile` de `api` copie `src/cv_builder` a su
imagen, así que se **portó** (no se importó) la validación de
`claim_rules` a `data_repo_write/claim_language.py`. El detalle completo,
y el porqué de cada decisión, está en
`docs/decisions/fase-2-perfil-editable.md`.

Dos hallazgos nuevos de `ruamel.yaml`, ninguno visto en M0/M1 porque
ningún fichero anterior tenía estas formas: un `null` explícito se volvía
a escribir en blanco con la sola secuencia cargar→volcar -corregido
registrando un representador de `None` en `yaml_style.data_repo_yaml()`-,
y un escalar plano de una sola línea por encima de 80 caracteres se
partía en dos al volcar -corregido ensanchando `yaml.width`, comprobado
que no rompe el round-trip de los campos plegados de los otros ficheros-.
Los cinco ficheros reales, más `config/cv_variants.yaml`, se comprobaron
byte a byte tras el arreglo.

Alcance confirmado con Pablo el 2026-09-07: en bullets, solo
`text_en`/`evidence_status`/`cv_usage` son editables por fila (`bullet_id`
casa la edición, el resto pasa intacto); alta sí, baja no, y una fila
nueva no fabrica una `confidentiality_status` que nadie ha confirmado. Las
5 claves de `variants` en `role_variant_content.yaml` son fijas -esta
rebanada no da de alta ni de baja variantes, solo edita su contenido-.
`evidence_status`/`cv_usage` pasan a ser vocabulario de código
(`data_repo_write/vocabularies.py`), cerrados con los valores que
`profile/project_catalog.yaml` ya documenta para el mismo concepto. La
"revisión de redacción de las afirmaciones de estado" de
`ARCHITECTURE.md` §14 se investigó de nuevo y sigue confirmada -sin
ningún bullet bloqueado-: se enseña de solo lectura en la pestaña de
Bullets, sin flujo editorial nuevo.

`/perfil` pasa a tener cinco pestañas -Objetivos, Preferencias,
Restricciones, Bullets, Variantes de rol-.

Verificado en esta máquina el 2026-09-07: `make check` limpio (402 tests
API -38 nuevos- + 17 web), `make e2e` con los 23 tests en verde
-incluidos los 3 nuevos de `perfil.spec.ts`-, capturas de pantalla de las
dos pestañas nuevas revisadas a mano, y el remoto de git local resembrado
tras ampliar el fixture de escritura -mismo precio que M1 ya documentó-.

**Sin verificar, y no se puede desde aquí:** lo mismo que M0/M1 -la
deploy key de verdad y el directorio en la VM de producción-, sin cambios
desde entonces.

### M3 — `config/cv_variants.yaml` y `profile/project_catalog.yaml`, cerrada el 2026-09-07

Investigado antes de escribir código: los dos ficheros (179 y 249
líneas) seguían sin tocarse desde el 2026-08-13 y con el tamaño
previsto, pero dos supuestos del troceo no se sostuvieron.
`project_catalog.yaml` tiene **8 proyectos, no 9** -el noveno que se
contaba es `discovery_backlog`, que el propio fichero declara que no
son proyectos-. Y `exclusive_evidence` de `cv_variants.yaml` -se creía
que referenciaba `project_id` de `project_catalog.yaml`, como
`professional_project_priority`/`public_project_priority`- en realidad
referencia un **`bullet_id`** de `professional_bullet_bank.yaml`: la
validación cruzada tiene dos espacios de nombres distintos, no uno. El
detalle completo, y el porqué de cada decisión, está en
`docs/decisions/fase-2-perfil-editable.md`.

`profile/project_catalog.yaml` no tenía modelo Pydantic ni ningún
camino de lectura en esta app hasta ahora -confirmado por grep-.
Documenta su propio vocabulario de `cv_usage`/`interview_usage`
(`eligible`/`conditional`/`blocked`), distinto del de `BulletCvUsage`
que M2 cerró para el banco de bullets aunque comparta nombre de campo;
`ProjectCvUsage` es un enum nuevo. Su `evidence_status`, en cambio, sí
reutiliza `BulletEvidenceStatus` tal cual -mismo concepto, y es
precisamente el fichero del que M2 lo tomó-.

Alcance confirmado con Pablo el 2026-09-07, las tres opciones
recomendadas: `claim_rules` de `cv_variants.yaml` queda de solo lectura
-M2 ya depende de él como barrera externa, a diferencia del criterio
permisivo que sí se le dio a `hard_constraints` en M1-;
`quant_exploratory` -la única variante de `base_variants` con `status`
en vez de las listas de prioridad, sin contraparte en
`role_variant_content.yaml`- queda de solo lectura y fuera de la
validación cruzada; y los campos atípicos de las 5 variantes activas
(`display_name`, `target_role_condition`, `note`, `exclusive_evidence`)
son de solo lectura, mismo patrón que los campos no gestionados de
`Bullet` en M2. En `project_catalog.yaml`: `project_id` casa cada
edición, sin alta ni baja -`discovery_backlog` queda fuera-, y solo
`safe_name`/`evidence_status`/`cv_usage`/`interview_usage`/
`pending_confirmations` son editables por fila.

La validación cruzada al guardar `cv_variants.yaml` comprueba, contra
los otros tres ficheros ya sincronizados en el mismo clon: que cada
`bullet_id` en `candidate_bullet_priority`/`exclusive_evidence` exista
en el banco de bullets; que cada `project_id` en
`professional_project_priority`/`public_project_priority` exista en el
catálogo; y que las claves de `role_variant_content.yaml` sean
subconjunto de las variantes activas -inclusión, no igualdad-. Se deja
para cuando haga falta de verdad: que el `project_id` esté en el lado
correcto (`professional_project_priority` solo con proyectos
`professional`, etc. -hoy se cumple, no se fuerza-), que un bullet
referenciado esté además en estado elegible para CV (ya lo filtra
`cv_builder.build.resolve_variant` al generar), y la semántica de
"exclusividad" real de `exclusive_evidence` entre variantes.

Los dos ficheros reales, y la validación cruzada completa, se
comprobaron contra el `career-strategy` real -no solo el fixture-:
`current()` los carga, valida y vuelve a volcar **idénticos byte a
byte**, sin ningún hallazgo nuevo de `ruamel.yaml`; y la validación
cruzada corrida contra los cinco ficheros reales a la vez no encontró
ninguna referencia rota.

`/perfil` pasa a tener siete pestañas -Objetivos, Preferencias,
Restricciones, Bullets, Variantes de rol, Variantes de CV, Catálogo de
proyectos-.

Verificado en esta máquina el 2026-09-07: `make check` limpio (435
tests API -33 nuevos- + 17 web), `make e2e` con los 25 tests en verde
-incluidos los 2 nuevos de `perfil.spec.ts`-, capturas de pantalla de
las dos pestañas nuevas revisadas a mano, y el remoto de git local
resembrado tras ampliar el fixture de escritura -mismo precio que M1/M2
ya documentaron-.

**Sin verificar, y no se puede desde aquí:** lo mismo que M0/M1/M2 -la
deploy key de verdad y el directorio en la VM de producción-, sin
cambios desde entonces.

### M4 — `config/scoring_model.yaml`, cierra Fase 2, cerrada el 2026-09-08

Investigado antes de escribir código: seguía en v2 (309 líneas, 15 claves
de primer nivel), sin tocar desde el cierre de Fase 1 M2. Las tres
interpretaciones que Fase 1 M2 dejó como código sin declarar en el YAML
-`very_low` → `aspirational`, el orden de evaluación de los cubos, el
estrechamiento de `cheap`- siguen, las tres, confirmadas en prosa dentro
de `portfolio_assignment.note`/`output.effort_tier.note` y no en forma
legible por máquina; ninguna pasó a ser un dato que el código lea. Hallazgo
no previsto: la nota de `cheap` seguía diciendo «pendiente de implementar
en futuro-app» dos días después de que `scoring.py` ya lo implementara -una
prueba en vivo de que la prosa puede desincronizarse de la realidad sin que
nadie lo note-.

**Decidido con Pablo el 2026-09-08, la opción recomendada de las tres
planteadas**: el bloque que documenta en prosa umbrales que en realidad
decide a mano `assessment/scoring.py` (`portfolio_assignment` entero,
cada nivel de `output.effort_tier`, `missing_data.rule/method/coverage/
below_minimum`, `output.required_fields`) queda de solo lectura, mismo
criterio que `claim_rules`/`fixed_sections` en M3 -abrirlo a edición no
cambiaría el cálculo real, solo el riesgo de que la prosa mienta más-. La
excepción es `output.effort_tier.evaluation_order`: sí lo recorre de
verdad `_effort_tier`, así que se edita como reordenación pura de las
cuatro etiquetas de `EffortTier`, sin alta ni baja. `version`/`status`
también de solo lectura -ningún código los lee, y `version` es un hito con
nombre que Pablo sube a mano, no un contador de ediciones-. El resto -
`weights`/`anchors` (alta, baja y renombrado de dimensión libres),
`gates` (igual, sin claves de criterio fijas), `baseline_madrid` (sus
campos, no su nombre), `description`, `portfolio_policy` y `notes`- es
editable sin puerta de vocabulario; `probability_bands` tiene las cuatro
claves fijas (vocabulario de código) con el texto libre.

Tres hallazgos nuevos de `ruamel.yaml`, ninguno visto en M0-M3: reasignar
un escalar **numérico** sin comprobar antes si cambió pierde formato igual
que un texto (`minimum_coverage: 0.50` → `0.5`); estampar la misma fecha en
dos sitios (`updated_at` del documento y de `baseline_madrid`) con el
mismo objeto de Python produce un ancla/alias YAML y de paso pierde una
línea en blanco vecina -corregido con `.replace()`-; y `notes` es una
lista de párrafos en bloque plegado, no de líneas cortas, así que necesitó
su propio `set_folded_list_if_changed`. Detalle completo, con líneas
exactas, en `docs/decisions/fase-2-perfil-editable.md`.

Sin validación cruzada con otros ficheros -a diferencia de M3-: ninguna
referencia de `scoring_model.yaml` a otro fichero es un identificador que
el código resuelva.

`/perfil` pasa a tener ocho pestañas -las siete de M3 más «Modelo de
scoring»-.

Verificado en esta máquina el 2026-09-08: `make check` limpio (465 tests
API -30 nuevos- + 17 web), `make migrate-check` limpio, `make e2e` con los
26 tests en verde -incluido el de editar el peso de una dimensión y las
ocho pestañas-, captura de pantalla de la pestaña nueva revisada a mano, y
`config/scoring_model.yaml` real vuelto a volcar idéntico byte a byte sin
ninguna edición.

**Sin verificar, y no se puede desde aquí:** lo mismo que M0-M3 -la deploy
key de verdad y el directorio en la VM de producción-, sin cambios desde
entonces.

## Fase 2 cerrada, en código

Las cinco rebanadas -shell mínimo, M0, M1, M2, M3 y M4- están hechas y
verificadas en esta máquina. `/perfil` edita hoy los ocho ficheros YAML
que Fase 2 se propuso cubrir, todos por el mismo mecanismo genérico de
`git_ops.py` que M0 cerró el primer día y que ninguna rebanada posterior
tuvo que tocar: `pull --rebase` → `ruamel.yaml` → validar → diff →
confirmar → commit → push.

**Confirmado, no solo asumido**: `ARCHITECTURE.md` (repositorio privado)
dice de Fase 2 que «al guardar, CI recompila las variantes afectadas».
`career-strategy/.github/workflows/build-cvs.yml` dispara en `push` a
`dev` sobre exactamente las rutas que M2/M3 hicieron editables
(`cv/content/professional_bullet_bank.yaml`, `cv/content/
role_variant_content.yaml`, `config/cv_variants.yaml`) — como
`commit_and_push` empuja directo a `dev` del repositorio privado, esto ya
pasa solo, sin ningún código nuevo en `futuro-app`. `config/
scoring_model.yaml` no está en esa lista de rutas, correctamente: no
afecta a qué CV se genera, solo a qué variante se recomienda.

**Deliberadamente fuera de las cinco rebanadas**, sin cambios desde que se
troceó la fase el 2026-09-06: `profile/master_profile.md`,
`profile/evidence_bank.md`, `profile/project_audits/*.md` y
`cv/master/Pablo_Coma_CV_master.tex.jinja2`. Son prosa en Markdown o
LaTeX, no YAML, y `ARCHITECTURE.md` acota Fase 2 a "los YAML del
repositorio privado". Si algún día hace falta editarlos desde la app, es
una decisión de UX distinta -edición de texto libre, o subir/reemplazar
el documento entero- y no el editor de formularios con diff que
construyó esta fase.

**Pendiente, no bloqueante para seguir en código, sí para llevar Fase 2 a
producción**: la deploy key de lectura-escritura y el directorio en la VM
(`docs/deployment.md` §10), pendiente desde M0 de que Pablo lo ejecute.

## Fase 3 — Pipeline y seguimiento (en curso)

Según `ARCHITECTURE.md` (repositorio privado), Fase 3 es «estados,
interacciones, recordatorios y el bot de Telegram avisando e ingiriendo
ofertas».

Investigado antes de trocear, el 2026-09-08: `docs/APP_SCREENS.md`
§Pipeline describe tres vistas intercambiables (tabla densa, mapa valor ×
probabilidad, kanban por etapa); §Hoy es una cola de decisiones agrupada
por tipo de pendiente. Ninguna de las dos tenía pantalla real -`/ofertas`
era el listado plano de Fase 1 M1, con su propio código admitiéndolo-.
Telegram no tiene ni una línea de código en ningún repositorio, solo
prosa. `applications` (Fase 1 M3) es hoy solo el dossier de variante
confirmada, sin nada de estado, interacción ni recordatorio.

**Troceo confirmado con Pablo el 2026-09-08, en ocho rebanadas** -más que
las cinco de Fase 2 a propósito: Pablo pidió que cada sesión termine en
torno al 30-40% de uso de contexto, así que se separa lo exploratorio
(una decisión de modelo de datos, una vista nueva tipo kanban, una
integración externa) en piezas más pequeñas que en Fase 2-. Orden por
dependencia real:

1. **Modelo de estados de candidatura. Cerrada** el 2026-09-08 (ver
   abajo).
2. **Pipeline: tabla densa** -sustituye `/ofertas` por la pantalla
   Pipeline de verdad, con filtros/orden sobre el estado de la rebanada 1.
3. **Pipeline: mapa valor × probabilidad.**
4. **Pipeline: kanban por etapa.**
5. **Interacciones** -registro manual por candidatura, visible en la
   pantalla Oferta-.
6. **Recordatorios** -`follow_up_at` y su gestión-.
7. **Pantalla Hoy** -la cola de decisiones, agregando 1-6-.
8. **Bot de Telegram** -probablemente en dos sesiones cuando llegue:
   ingesta y avisos por separado-.

Sigue siendo razonable ajustar el troceo si la realidad no encaja al
llegar a una rebanada concreta.

### Cómo se trabaja esta fase

Mismas reglas que Fase 2: una rebanada, una sesión de Claude Code, de
punta a punta, con su propia entrada en `docs/decisions/fase-3-*.md` al
cerrarla, y `NEXT_SESSION.md` reescrito con el estado comprobado antes de
cerrar la sesión. Empezar proponiendo el diseño y esperando el visto
bueno antes de escribir código.

### Rebanada 1 — Modelo de estados de candidatura, cerrada el 2026-09-08

A diferencia de toda Fase 2, **no toca el repositorio privado `Futuro` en
ningún momento**: el estado de una candidatura es dato operativo propio
de esta aplicación. El detalle completo, con el porqué de cada decisión,
está en `docs/decisions/fase-3-estados-de-candidatura.md`.

**Decisión de fondo:** tabla nueva, `offer_status_events` (migración
`0004`), hermana de `applications` y no un `ALTER TABLE` aditivo sobre
ella como anticipaba el docstring de Fase 1 M3. El estado
(`research`/`preparing`/`submitted`/`interview`/`closed`, vocabulario de
código cerrado en `docs/OFFER_DATA_CONTRACT.md`) empieza antes de que
exista ninguna variante confirmada, y `applications.variant`/`cv_sha256`
son `NOT NULL` desde el primer día: mezclar las dos cosas habría exigido
hacerlos nullable. Cuelga de `capture_id`, append-only con el mismo
trigger de inmutabilidad, "vigente" = la última fila por
`(occurred_at DESC, id DESC)` -mismo patrón que `applications`-. Sin
`submitted_at` ni columnas parecidas: son el `occurred_at` de la fila
donde el estado tomó ese valor.

Tres preguntas resueltas con Pablo antes de escribir código, las tres
como se propusieron: transiciones libres sin máquina de estados en la
base de datos; confirmar una variante no mueve el estado solo -gestos
separados, hueco conocido y no bloqueante-; sin campo de texto libre en
la transición -eso espera a la rebanada 5-.

`futuro_api/pipeline/` es el paquete nuevo (vocabulario, modelo,
repositorio, vistas); las rutas viven en `offers/router.py`, mismo
patrón que ya sigue `applications`. `/ofertas` gana la etiqueta de
estado por fila; `/ofertas/[id]` gana la sección «Estado de la
candidatura», un botón por etapa sin desplegable, mismo criterio que
`VariantOptionRow`.

Verificado en esta máquina el 2026-09-08: `make check-api` limpio (484
tests -19 nuevos-), `make migrate-check` limpio con la migración `0004`,
`make check-web` limpio (17 tests), y `make e2e` con las 29 pruebas en
verde -3 nuevas-. Hallazgo menor de la suite entera, no de esta rebanada,
anotado en el documento de decisiones: dos marcas `ref-${Date.now()}` casi
simultáneas pueden deduplicar dos capturas de pruebas distintas cuando se
ejecutan muy pocas pruebas en paralelo; con la suite completa
(`make e2e`, 5 workers) no se reprodujo.

**Sin verificar, y no se puede desde aquí:** nada nuevo -esta rebanada no
toca el repositorio privado ni la deploy key de escritura-.

Siguiente: **rebanada 2 — Pipeline: tabla densa**, sustituyendo el
listado plano de `/ofertas` por la pantalla Pipeline de verdad, con
filtros/orden sobre el estado que esta rebanada acaba de introducir.
