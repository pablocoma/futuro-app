# Traspaso a la siguiente sesión

Última actualización: 2026-09-13.

Este archivo es **solo el estado operativo actual y el troceo de la fase en
curso**: se reescribe en cada cierre de rebanada, no acumula historial. El
porqué de cada decisión ya cerrada —qué se integró, desviaciones
deliberadas, alcance dejado fuera a propósito— vive en
`docs/decisions/fase-<n>-*.md`, un fichero por fase que sí se acumula y no
se poda; no se duplica aquí. Las reglas duraderas de cómo se trabaja en
este repositorio están en `AGENTS.md`, tampoco aquí.

El hook de arranque de sesión ya vuelca este archivo y `README.md` enteros
en el contexto: no hace falta releerlos con la herramienta de lectura salvo
sospecha de que están desactualizados.

## Estado por fase

- **Fase 0.5** (generador de CVs en Python/Jinja2, ejecutado en CI del
  repositorio privado) — cerrada 2026-09-03.
  `docs/decisions/fase-0.5-workflow-de-cvs.md`.
- **Fase 1** (núcleo: pegar oferta → extraer → puntuar → recomendar
  variante → PDF) — cerrada y **en producción** desde 2026-09-05.
  `docs/decisions/fase-1-nucleo.md`.
- **Fase 2** (perfil editable: los ocho YAML del repositorio privado) —
  cerrada en código el 2026-09-08. `docs/decisions/fase-2-perfil-editable.md`.
  **Pendiente de aprovisionar a mano en producción**: deploy key de
  lectura-escritura, `docs/deployment.md` §10. Corrección el 2026-09-13 en
  `git_ops.py`, **confirmada y cerrada**: el bloqueo del *event loop* por
  un `subprocess.run` síncrono escondía una carrera real de git bajo carga
  concurrente -`/perfil` fallaba el 100% de las veces en CI y en local con
  varias pestañas a la vez-; verificado en esta máquina y contra dos
  ejecuciones reales de la CI de GitHub Actions, cero errores de git en
  ambas. Ver la sección fechada de ese día en el mismo fichero de
  decisiones.
- **Fase 3** (pipeline y seguimiento) — en curso desde 2026-09-08. Troceo
  y siguiente objetivo abajo.
  `docs/decisions/fase-3-pipeline-y-seguimiento.md` —lee solo su sección
  más reciente salvo que necesites revisar una decisión anterior
  concreta; el índice de secciones del propio fichero dice cuál—.

## Producción

`https://futuro-pc.duckdns.org`, desde 2026-09-05. Cada merge a `main`
despliega: build arm64 → GHCR, SSH a la VM de Oracle, clon de solo lectura
del repositorio de datos, migraciones, comprobación de salud, rollback al
tag anterior si falla. `main` está protegida (PR obligatorio, checks de
`ci.yml`, historial lineal). Valores concretos (IPs, secretos, tokens) en
`Futuro/docs/INFRASTRUCTURE.md`, nunca aquí.

**Cabos sueltos:**

- **Revisar `docs/deployment.md` §10 antes de aprovisionar la deploy key
  de escritura.** Hallazgo lateral del 2026-09-13 al cerrar el bloqueante
  de `e2e` (ver `docs/decisions/fase-2-perfil-editable.md`, sección de ese
  día): sus pasos de "Provisionar, en orden" no crean
  `/opt/futuro/data/repo-write` con permisos que el `uid 10001` de `api`
  pueda escribir, y el `chmod 600` de la deploy key privada -propietario
  "el usuario de deploy"- dejaría al contenedor sin poder leerla en
  absoluto. No bloquea nada hoy porque esa deploy key todavía no se ha
  aprovisionado; sí bloqueará el día que se intente sin corregir esto
  primero.
- Sin `pg_dump` de producción todavía (`ARCHITECTURE.md` §12 lo pide
  diario, cifrado, 30 días de retención).
- Aviso por Telegram del resultado del deploy: pendiente hasta la
  rebanada 8 de Fase 3 (el bot).
- `enforce_admins` desactivado a propósito en la protección de `main`,
  para poder desbloquear un deploy urgente si un check se rompiera por
  causas ajenas.
- `career-strategy/.github/workflows/build-cvs.yml` sigue fijado a
  `ref: dev` (rama mutable); ahora que `main` está protegida y estable,
  se puede fijar una referencia concreta cuando convenga. No bloqueante.

## Fase 3 — Pipeline y seguimiento

Según `ARCHITECTURE.md` (repositorio privado): «estados, interacciones,
recordatorios y el bot de Telegram avisando e ingiriendo ofertas».

**Troceo acordado con Pablo el 2026-09-08, ocho rebanadas** —más fino que
las cinco de Fase 2 a propósito: cada sesión debe terminar con holgura de
contexto (en torno al 30-40% de uso), así que lo exploratorio (una
decisión de modelo de datos, una vista nueva, una integración externa) va
en piezas más pequeñas que lo mecánico. Orden por dependencia real, no por
tamaño. Ajustable si la realidad no encaja al llegar a una rebanada
concreta.

1. ~~Modelo de estados de candidatura~~ — **cerrada 2026-09-08.**
2. **Pipeline: tabla densa** ← siguiente objetivo, ver abajo.
3. Pipeline: mapa valor × probabilidad.
4. Pipeline: kanban por etapa.
5. Interacciones (registro manual por candidatura).
6. Recordatorios (`follow_up_at`).
7. Pantalla Hoy (cola de decisiones agrupada por tipo de pendiente).
8. Bot de Telegram (probablemente dos sesiones: ingesta y avisos).

### Siguiente objetivo: rebanada 2 — Pipeline, tabla densa

Sustituir el listado plano de `/ofertas` (Fase 1 M1) por la pantalla
Pipeline real que describe `docs/APP_SCREENS.md` (repositorio privado)
§Pipeline, en su vista de tabla densa (mapa y kanban son las rebanadas 3
y 4, no esta).

**Investigación ya hecha, diseño concreto propuesto a Pablo el
2026-09-13, pendiente de su visto bueno para empezar a escribir código:**

Decidido con Pablo esa misma sesión: sin selector de vistas todavía
(rebanada 3 lo trae con la primera vista alternativa de verdad); sin
paginación por cursor para esta vista (se quita `before`, todo cabe en
el límite actual de 100 filas, ordenado/filtrado en la propia consulta
SQL); sin buscador de texto libre (solo filtros estructurados); las
ofertas sin puntuar van siempre al final del orden por `value_score`,
sea cual sea el sentido (`NULLS LAST`); se añade `assessment_status` a
la fila además de los tres campos de `offer_assessments` -si no, un
`value_score` nulo es ambiguo entre «sin puntuar», «en cola» y «falló»-.

- **Backend:**
  - `assessment/repository.py`: nuevo `current_assessments_for(session,
    extraction_ids)` — mismo patrón `DISTINCT ON` que
    `offers_repo.current_extractions_for`/`pipeline_repo.current_statuses_for`.
  - `offers/views.py::OfferSummaryView`: añade `value_score`,
    `probability_band`, `portfolio_bucket`, `assessment_status` (opcionales,
    `None` mientras no haya assessment).
  - `offers/router.py::list_offers`: añade query params `status`,
    `posting_status`, `portfolio_bucket` (filtros) y `sort`/`order`
    (`captured_at`/`value_score`/`title`/`company`). Un `LEFT JOIN` a
    `offer_assessments` cubre orden y filtro en una sola consulta.
- **Frontend:**
  - `/ofertas/page.tsx` pasa de lista plana a tabla densa: puesto/empresa,
    estado de candidatura, `value_score` (número grande, sin escala —
    micro-decisión ya establecida), probabilidad, cartera, estado del
    anuncio, capturada.
  - Orden y filtro por `searchParams` (patrón nuevo en este repo:
    cabeceras de columna como enlaces, sin JS de cliente) — sigue el
    criterio de la app de server components sobre estado de cliente.
  - Se promueve el componente `State` (etiqueta + subrayado de color),
    hoy sin exportar dentro de `ofertas/[id]/page.tsx`, a
    `components/State.tsx` compartido.
  - `/ofertas/[id]` no cambia. La ruta `/ofertas` se queda donde está
    (`Shell.tsx` ya la trata como «Pipeline»).
- **Tests:** extender `test_offers_api.py` (sort/filter/campos nuevos) y
  revisar `e2e/tests/pipeline_status.spec.ts` -asume hoy un listado plano
  en `/ofertas`, puede necesitar ajuste si el marcado cambia lo bastante.

Fuera de esta rebanada a propósito: selector de vistas, búsqueda de texto
libre, mapa y kanban.
