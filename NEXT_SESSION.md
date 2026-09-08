# Traspaso a la siguiente sesión

Última actualización: 2026-09-09.

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
  lectura-escritura, `docs/deployment.md` §10.
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

**Cabos sueltos, ninguno bloqueante:**

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

Antes de proponer diseño, investigar:

- Qué dice exactamente esa sección sobre la tabla densa (ordenable y
  filtrable) y sobre el selector que algún día alternará las tres
  vistas —¿se construye ya aunque las otras dos no existan todavía?—.
- Qué de lo necesario para filtrar/ordenar ya expone `GET /api/offers`
  (`status` desde la rebanada 1, `posting_status`) y qué falta
  (`value_score`/`probability_band`/`portfolio_bucket` de
  `offer_assessments`, de Fase 1 M2).
- Si conviene mantener la ruta `/ofertas` o moverla, dado que
  `/ofertas/[id]` sigue siendo la pantalla de detalle sin cambios
  previstos en esta rebanada.

Proponer el diseño concreto y esperar el visto bueno antes de escribir
código.
