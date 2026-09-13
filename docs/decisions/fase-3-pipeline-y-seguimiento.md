# Fase 3 — Pipeline y seguimiento

Ver `ARCHITECTURE.md` (repositorio privado `Futuro`) §14 para el alcance de
la fase: «estados, interacciones, recordatorios y el bot de Telegram
avisando e ingiriendo ofertas». El troceo en ocho rebanadas se acordó con
Pablo el 2026-09-08 y está en `NEXT_SESSION.md`. Este documento recoge solo
las decisiones de implementación tomadas aquí, y se amplía con cada
rebanada, mismo criterio que `docs/decisions/fase-2-perfil-editable.md`.

## 2026-09-08 — Rebanada 1, modelo de estados de candidatura

A diferencia de toda Fase 2, **esta rebanada no toca el repositorio privado
`Futuro` en ningún momento**: el estado de una candidatura es dato operativo
propio de esta aplicación, no un YAML de perfil. No hay `pull --rebase`, no
hay `git_ops.py`, no hay deploy key de escritura implicada.

### La investigación, antes de diseñar

- `docs/APP_SCREENS.md` (repositorio privado) §Pipeline y §Hoy: Pipeline
  describe tres vistas intercambiables (tabla densa, mapa valor ×
  probabilidad, kanban por etapa) sobre un selector único; Hoy es una cola
  de decisiones agrupada por tipo de pendiente. Ninguna de las dos tenía
  pantalla real: `/ofertas` era el listado plano de Fase 1 M1, con su
  propio código admitiéndolo (`ofertas/page.tsx` decía literalmente que
  esperaba a esta fase).
- Telegram: cero código en cualquiera de los dos repositorios -ni webhook,
  ni token, ni librería-. Es prosa en `ARCHITECTURE.md` y `APP_SCREENS.md`,
  nada más. Confirma que es una rebanada entera propia (la última de las
  ocho), no un cabo suelto de Fase 1.
- `applications` (Fase 1 M3) es hoy solo el dossier -`capture_id`,
  `recommendation_id`, `variant`, `cv_sha256`, `confirmed_at`-, `NOT NULL`
  en `variant`/`cv_sha256` desde el primer día, y su propio docstring
  anticipaba que Fase 3 añadiría `status`/`channel`/`submitted_at`/
  `follow_up_at`/`outcome` con un `ALTER TABLE` aditivo sobre esa misma
  tabla.

### La decisión de fondo: tabla propia, no `ALTER TABLE` sobre `applications`

Se revisa la nota de M3 y no se sigue. El estado de una candidatura -según
`docs/OFFER_DATA_CONTRACT.md`, `research → preparing → submitted →
interview → closed`- empieza **antes** de que exista ninguna variante
confirmada: `research` es "lo estoy considerando", y `applications` no
puede tener una fila hasta que haya un PDF concreto detrás. Meter las dos
cosas en una tabla habría exigido hacer `variant`/`cv_sha256` nullable y
mezclar dos eventos distintos -cambiar de variante, cambiar de etapa- en
una sola fila.

**Decisión: `offer_status_events`, hermana de `applications` y no una
columna sobre ella.** Cuelga de `capture_id`, igual que el dossier:
append-only con el mismo trigger de inmutabilidad instalado en 0001,
"vigente" es la última fila por `(occurred_at DESC, id DESC)`, mismo
patrón exacto que `applications.repository.current_application`. No hay
columna `submitted_at`: es el `occurred_at` de la fila donde el estado
tomó ese valor, y lo mismo valdría para un futuro `interview_at` sin tocar
el esquema. Migración `0004`, con el docstring explicando la desviación
frente a lo que anticipaba `0003`.

### Tres preguntas resueltas con Pablo antes de escribir código

- **Transiciones libres, sin máquina de estados en la base de datos.**
  Cualquier valor a cualquier otro es válido -de `research` directo a
  `closed`, por ejemplo, sin pasar por las etapas intermedias-. Encaja con
  que el kanban de `docs/APP_SCREENS.md` se arrastra a mano; una restricción
  de orden es una decisión aparte si algún día hace falta.
- **Confirmar una variante no mueve el estado.** `POST
  /api/offers/{id}/dossier` y `POST /api/offers/{id}/status` son gestos
  completamente separados; no hay ningún avance automático. Cubierto por
  `test_confirming_a_variant_does_not_move_the_pipeline_status`. Hueco
  conocido y no bloqueante, igual que la ausencia de concurrencia optimista
  que ya quedó anotada en Fase 2 M0: si en la práctica resulta incómodo
  tener que marcar `preparing` a mano tras confirmar, es una rebanada
  futura, no un descuido de esta.
- **Sin campo de texto libre en la transición.** Ni motivo de cierre ni
  nota rápida: quedan para cuando llegue la rebanada de interacciones
  (Fase 3, rebanada 5), que es donde vive ese concepto.

### El mecanismo

`futuro_api/pipeline/` es un paquete nuevo -`vocabularies.py`
(`ApplicationStatus`, vocabulario de código sin ningún YAML detrás),
`models.py` (`OfferStatusEvent`), `repository.py` (`record_status`,
`current_status`/`current_status_event`, `current_statuses_for` en bloque
para el listado con `DISTINCT ON`, mismo patrón que
`offers_repo.current_extractions_for`, y `status_history`), `views.py`-.
Los endpoints viven en `offers/router.py` y no en un `router.py` propio del
paquete nuevo: es el patrón que ya sigue `applications` -modelos y
repositorio en su propio paquete, rutas en el router de ofertas-, así que
se mantiene en vez de introducir una segunda convención.

`GET /api/offers` gana `status` por fila (`research` por defecto sin
ningún evento); `GET /api/offers/{id}` gana `status` y `status_history`
completo, de la más reciente a la más antigua. `POST
/api/offers/{id}/status` registra una transición y devuelve el evento
nuevo.

En pantalla: una sección «Estado de la candidatura» en `/ofertas/[id]`,
justo debajo de la cabecera y antes de cualquier contenido que dependa de
extracción o puntuación -el estado no depende de ninguna de las dos-. Un
botón por etapa en vez de un desplegable, mismo criterio que
`VariantOptionRow`: la etapa vigente se enseña marcada y sin botón propio,
las demás son un `<form>` con acción de servidor, sin JavaScript propio.
`/ofertas` gana la etiqueta de estado junto a la de extracción en cada
fila.

### Verificado en esta máquina, 2026-09-08

`make check-api` limpio (484 tests -19 nuevos: 6 de repositorio, 8 de
router, 1 de que confirmar variante no mueve el estado, 3 de esquema-
inmutabilidad, rechazo de un valor fuera del vocabulario, y que borrar la
captura se lleva su historial-, más una fila nueva ya cubierta por el test
genérico `test_vocabularies_match_the_database`), `make migrate-check`
limpio con la migración `0004`, `make check-web` limpio (17 tests, uno
ampliado para cubrir `APPLICATION_STATUS_LABELS`), y `make e2e` con las 29
pruebas en verde -3 nuevas: estado por defecto visible en la oferta y en
el listado, cambiar de etapa se refleja en los dos sitios, y una transición
sin pasos intermedios-.

**Hallazgo menor, no de esta rebanada sino de la suite entera, anotado y no
corregido aquí:** las tres pruebas nuevas, ejecutadas solas con
`--workers=3` (fuera del `make e2e` real, que usa 5 workers sobre los 29
tests), colisionaron una vez por dos marcas `ref-${Date.now()}` casi
simultáneas -mismo patrón que ya usan `oferta.spec.ts`, `dossier.spec.ts`,
`puntuacion.spec.ts` y `perfil.spec.ts`-: dos capturas con el mismo
milisegundo producen el mismo `raw_text_sha256` y la API deduplica,
haciendo que dos pruebas operen sobre la misma fila sin saberlo. Con la
suite completa (`make e2e`, 5 workers, 29 tests) no volvió a pasar. No se
toca aquí porque es un riesgo latente y preexistente de la convención
entera de marcado, no algo que esta rebanada introdujera; conviene tenerlo
presente si algún día `make e2e` empieza a fallar de forma intermitente en
un test con `ref-${Date.now()}`.

### Deliberadamente fuera de esta rebanada

- La pantalla Pipeline en sí -tabla densa (rebanada 2), mapa valor ×
  probabilidad y kanban por etapa (rebanadas 3-4)-: esta rebanada solo
  puso el dato y un control mínimo en `/ofertas`/`/ofertas/[id]`.
- Cualquier nota o motivo asociado a una transición (rebanada 5,
  interacciones).
- `follow_up_at` y recordatorios (rebanada 6).
- Mover el estado automáticamente al confirmar una variante.
- Restringir qué transiciones son válidas.

## 2026-09-13 — Rebanada 2, Pipeline: tabla densa

Sustituye el listado plano de `/ofertas` (Fase 1 M1) por la vista de tabla
densa de `docs/APP_SCREENS.md` (repositorio privado) §Pipeline. Diseño
propuesto a Pablo y aprobado el mismo día -sin selector de vistas todavía
(rebanada 3 lo trae con la primera vista alternativa de verdad), sin
paginación por cursor, sin buscador de texto libre-.

### Backend

- `offers/router.py::list_offers` gana `status`, `posting_status`,
  `portfolio_bucket` (filtros) y `sort`/`order` sobre `captured_at`,
  `value_score`, `title`, `company`. `value_score` siempre manda las
  ofertas sin puntuar al final -`NULLS LAST`-, sea cual sea el sentido:
  un valor nulo no es "la peor nota", es "no hay nada que comparar
  todavía".
- `OfferSummaryView` añade `value_score`, `probability_band`,
  `portfolio_bucket` y `assessment_status`. Este último viaja aparte y no
  se infiere de `value_score`: un valor nulo es ambiguo entre «sin
  puntuar», «en cola» y «falló», y sin `assessment_status` la pantalla no
  podría distinguirlos. Reutiliza el tipo `ExtractionStatus` de
  `offers/views.py` en vez de importar `AssessmentStatus` de
  `assessment/views.py`: la dirección de las dependencias es
  `assessment` → `offers`, y este módulo no puede invertirla.

**Desviación deliberada sobre lo propuesto inicialmente.** La propuesta
original preveía un `assessment_repo.current_assessments_for` -bulk
`DISTINCT ON`, mismo patrón que `current_extractions_for`/
`current_statuses_for`- combinado en Python con una `list_captures`
paginada. Al escribir el código quedó claro que no encaja: quitar la
paginación por cursor significa que el corte de la página ahora depende
de filtro y orden configurables, así que **tiene que** hacerse en la
propia consulta SQL -aplicar `LIMIT` en Python después de traer una
página fija por `captured_at` deja de ser correcto en cuanto se ordena
por otra columna-. La solución real es `offers/repository.py::
list_offer_rows`: un único `SELECT` con tres subconsultas `DISTINCT ON`
-extracción, assessment y estado vigentes, cada una con el mismo orden
que su propio módulo ya usaba- unidas por `LEFT JOIN`, con filtro, orden
y límite todos en la misma consulta. Como consecuencia, `current_assessments_for`
nunca se llegó a escribir -no lo llama nadie-, y `list_captures`/
`current_extractions_for` -que solo `list_offers` usaba- se borraron en
vez de dejarlos muertos junto al código nuevo.

### Frontend

- `/ofertas/page.tsx`: tabla densa con las columnas puesto/empresa,
  candidatura, valor, probabilidad, cartera, anuncio y capturada. Orden y
  filtro viven en `searchParams` -cabeceras de columna y opciones de
  filtro son enlaces normales, patrón nuevo en este repositorio: sigue el
  criterio de la app de server components sobre estado de cliente, y
  aquí no hace falta ni un componente cliente-.
- Sin columna propia de "estado de extracción"/"estado de puntuación": no
  están en la lista de columnas que se acordó con Pablo. En vez de una
  columna más, la celda de puesto/empresa enseña el estado de extracción
  cuando todavía no hay título, y la celda de valor enseña
  `assessment_status` cuando `value_score` es nulo -es exactamente el
  motivo por el que se añadió ese campo a la API-.
- El componente `State` (etiqueta + subrayado de color), hasta ahora sin
  exportar dentro de `ofertas/[id]/page.tsx`, se promueve a
  `components/State.tsx` compartido, con la etiqueta ahora opcional: en
  el `<dl>` del detalle la lleva, en una celda de tabla -donde la
  cabecera ya dice qué es- no. De paso cambia sus `dt`/`dd` por
  elementos genéricos, porque el segundo uso no vive dentro de un
  `<dl>` y `dt`/`dd` sueltos ahí serían HTML inválido.
- `/ofertas/[id]` no cambia de comportamiento, solo de dónde importa
  `State`.

### Verificado en esta máquina, 2026-09-13

Backend: `uv run ruff check`/`ruff format --check`/`mypy` limpios, `uv run
pytest -q` en verde -495 tests, con los nuevos cubriendo orden por
`value_score` con `NULLS LAST` en los dos sentidos, filtro por
`posting_status`/`portfolio_bucket`/`status`, los campos nuevos del
listado, y un 422 en un `sort`/`order` inválido-, contra el Postgres real
de `make up`. Frontend: `npm run typecheck`/`lint`/`test` limpios (19
tests, 2 nuevos para la construcción de la query de `listOffers`), `npm
run build` sin avisos.

Verificado también contra el stack real (`docker compose up --build`, no
solo `make check`): capturas de pantalla de `/ofertas` con datos
sembrados por sesiones anteriores, filtros compuestos (candidatura +
cartera a la vez) y su estado vacío, y clic real sobre la cabecera
"Valor" comprobando que navega a `?sort=value_score&order=asc` y marca la
columna activa. `make e2e` completo: las 18 pruebas que tocan
`/ofertas`/`/ofertas/[id]`/shell pasan -incluida
`pipeline_status.spec.ts` entera-; las 2 que fallan y las 9 que no llegan
a correr son todas de `perfil.spec.ts` y de "Perfil es un destino real"
en `shell.spec.ts`, por un 409 "conflicto al traer «dev»" al leer
`/api/profile/objectives` -un conflicto de `git pull --rebase` en el
clon de trabajo local de Fase 2, en `.dev-data/repo-write`, acumulado por
sesiones anteriores en esta misma máquina-. No toca nada de esta
rebanada -que no lee ni escribe ese repositorio- ni el código que cambió;
es estado local de este `.dev-data`, no una regresión.
