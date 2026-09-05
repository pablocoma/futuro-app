# Fase 1 — El núcleo

Ver `ARCHITECTURE.md` (repositorio privado `Futuro`) §14 para el alcance
cerrado de la fase, y `docs/OFFER_DATA_CONTRACT.md` y `docs/APP_SCREENS.md`
del mismo repositorio para el contrato de datos y el diseño de pantallas.
Este documento recoge solo las decisiones de implementación tomadas aquí, y
se amplía con cada rebanada (M0 → M3).

La Fase 0 que `ARCHITECTURE.md` pone antes de la Fase 1 no se había
construido: al arrancar esta fase el repositorio solo contenía `cv_builder`.
M0 es esa Fase 0, absorbida como primera rebanada.

## 2026-09-03 — M0, el esqueleto

Compose local con `caddy`, `api`, `web` y `postgres`; `GET /api/health` con
su página; OAuth de Google con allowlist de un email; CI en `dev`; y el
workflow de deploy escrito. Cuatro de los seis servicios de
`ARCHITECTURE.md` §4: `redis` y `worker` no entran porque no tienen trabajo
que hacer hasta que haya llamadas al LLM, en M1.

**Decisión: `api` y `web` como proyectos separados bajo `services/`, no un
workspace con el `pyproject.toml` de la raíz.** El
`Futuro/.github/workflows/build-cvs.yml` que ya funciona construye
`docker/Dockerfile` con la raíz como contexto, y ese Dockerfile copia
`pyproject.toml`, `uv.lock` y `src/`. Convertir la raíz en un workspace de
uv habría movido `cv_builder` y roto un pipeline que está cerrado y probado.
El coste es tener dos `uv.lock` y dos harness, que es precisamente lo que
`AGENTS.md` pide para un componente con su propio ciclo de vida: `cv_builder`
se ejecuta en el CI de otro repositorio, la API en la VM.

**Decisión: la API se cierra por omisión, con lista explícita de rutas
públicas.** Un middleware deniega todo lo que no esté en `PUBLIC_PATHS` /
`PUBLIC_PREFIXES`, en vez de proteger ruta por ruta con una dependencia. Con
el patrón inverso, una ruta nueva de M1 queda abierta si alguien olvida la
dependencia; con este, queda protegida y el olvido se nota enseguida. Solo
`/api/health`, `/api/auth/*` y la documentación de OpenAPI son públicas.

**Decisión: el orden de registro de los middleware, explicado en el código.**
Starlette ejecuta primero el middleware añadido más tarde, así que
`SessionMiddleware` se registra **después** de la puerta de sesión para
quedar por fuera. Al revés —que es el orden que parece natural leyendo el
fichero— `request.session` no existe todavía cuando la puerta lo consulta.
Se descubrió porque el test `test_api_is_closed_by_default` falló con
`SessionMiddleware must be installed`; queda un comentario en `main.py`
porque es el tipo de error que se reintroduce al reordenar código.

**Decisión: la allowlist se revalida en cada petición, no solo al entrar.**
`current_user` comprueba el email de la sesión contra `ALLOWED_EMAILS`
siempre, no únicamente en el callback de OAuth. Así, quitar un email de la
allowlist cierra su sesión al instante en lugar de esperar a que caduque la
cookie, que con `session_max_age_seconds` de catorce días serían dos
semanas de acceso. Cubierto por
`test_session_of_an_email_removed_from_the_allowlist_stops_working`.

**Decisión: con `ENV=production`, la API no arranca con configuración de
desarrollo.** El validador de `Settings` exige credenciales de Google,
allowlist no vacía, `SESSION_SECRET` distinto del valor por defecto y
`PUBLIC_BASE_URL` en `https://`. Fallar en el arranque es preferible a
fallar en la primera petición que necesite el dato, y muy preferible a
levantar en producción con el bypass de desarrollo activo: `bypass_active`
exige además `env == "development"`, así que `DEV_AUTH_BYPASS=true` en
producción es inerte y no un agujero.

**Decisión: `/api/health` es pública y devuelve 503 con cuerpo.** La
consultan el healthcheck de Compose, Caddy y el paso de verificación del
deploy, ninguno con sesión. Cuando Postgres no responde devuelve 503 pero
con el cuerpo intacto (`status: degraded`, `database: unreachable`), y el
cliente del frontend conserva el cuerpo de un 503 a propósito: descartarlo
dejaría la página sin poder distinguir "API caída" de "base de datos
caída", que es justo la información que hace útil un esqueleto.

**Decisión: el healthcheck de Compose acepta 200 y 503.** Un 503 significa
"la API vive, Postgres no contesta". Marcar ese contenedor como no sano
sería contraproducente: es precisamente el que puede informar del fallo.

**Decisión: la página de M0 no es un "hola mundo".** Pinta el estado de los
cuatro servicios y de la sesión, renderizado en servidor. Es lo que hace
observable que Caddy enruta, que `web` habla con `api` por la red de
Compose y que la sesión que ve el navegador es la que ve el backend. Las
señales llevan símbolo además de color (`●` / `▲`), para no codificar
información solo en el color.

**Decisión: paleta "Plano técnico" sin conmutador de tema.** Los siete
tokens de `docs/APP_SCREENS.md` entran como variables de Tailwind v4 con sus
nombres del documento. `next-themes`, que `ARCHITECTURE.md` §8 menciona, no:
no hay paleta clara decidida, e inventarla aquí sería tomar una decisión de
diseño que no está tomada.

**Decisión: el E2E corre contra el Compose ya levantado, no contra un
servidor que arranque Playwright.** Lo que M0 tiene que garantizar es la
topología completa, y en particular que `/api/*` llega a FastAPI y el resto
a Next. El smoke test lo comprueba exigiendo que una ruta inexistente bajo
`/api` devuelva el 404 **en JSON** de FastAPI: si devolviese el 404 en HTML
de Next, el enrutado estaría al revés y ningún test unitario lo vería.

**Decisión: Alembic entra en M0 sin ninguna migración.** El deploy ejecuta
`alembic upgrade head`, así que la maquinaria tiene que existir para que ese
paso sea un no-op válido en vez de un comando que falla. Las tablas del
contrato de oferta son M1.

**Decisión: sin servicio de Postgres en el job de tests de la API.**
`ARCHITECTURE.md` §11 lo lista, pero los tests de M0 no lo necesitan —el
caso "base de datos caída" es uno de los que hay que cubrir, y el caso sano
se cubre sustituyendo el ping—. Arrancar un contenedor que nadie usa solo
alarga el CI. Entra cuando M1 traiga tablas y repositorios.

**Decisión: `gitleaks` en el CI desde el primer commit de la app.** El
primer principio de `AGENTS.md` es que aquí no entran datos personales.
`ARCHITECTURE.md` §15 ya lo listaba como mitigación; se monta ahora, no
cuando haya algo que filtrar.

### La cola y la persistencia

**Decisión: el repositorio no hace `commit`.** La frontera de la transacción
la decide quien llama, que es el único que sabe si el trabajo terminó. Un
repositorio que commitea por su cuenta deja medias extracciones guardadas
cuando el paso siguiente falla. Tampoco valida nada: lo que entra ya pasó
por `rules.validate`, y esa es la única puerta.

**Decisión: la llamada al modelo se hace fuera de la transacción que
guarda.** Una petición de treinta segundos con una transacción abierta
bloquearía filas todo ese rato para nada.

**Decisión: el coste se registra antes de validar, en su propia
transacción.** Si la validación rechaza la extracción, la llamada ya está
pagada y el gasto tiene que constar igual. Registrarlo solo cuando el
resultado sirve haría que el total mintiera justamente cuando el modelo se
porta mal, que es cuando más interesa saber lo que cuesta.

**Decisión: arq decide *cuándo* se reintenta y la tarea decide *si* tiene
sentido reintentar.** Una negativa del modelo o una extracción que incumple
el contrato darán lo mismo en el segundo intento: se marcan fallidas y no se
relanzan. Un fallo de red sí se relanza, hasta tres intentos. Mientras la
cola espera para reintentar, la fila vuelve a `queued` y no se queda en
`running`: nadie está ejecutando nada, y la pantalla no debe decir lo
contrario.

**Decisión: la fila de `job_runs` se guarda y se commitea antes de encolar.**
El orden no es el intuitivo, y el motivo es que el worker puede empezar a
ejecutar el trabajo en el mismo instante en que se encola: si la fila no
estuviera guardada, la tarea no encontraría su propio `job_run`. El riesgo
que deja este orden es el contrario —si el encolado falla después del
commit, queda una fila que nadie va a ejecutar— y eso lo recoge el barrido
de trabajos estancados. Es el fallo que se prefiere: visible y recuperable,
en lugar de un trabajo que se ejecuta contra una fila que no existe.

**Decisión: un barrido periódico da por perdidos los trabajos que llevan
quince minutos sin acabar.** Hace falta porque un trabajo puede desaparecer
sin dejar rastro: si Redis se reinicia, la cola se vacía y la fila se queda
en `queued` para siempre. Sin esto, la pantalla enseñaría «en cola» de por
vida y nadie sabría que hay que reintentar. Corre como `cron` de arq cada
cinco minutos y también al arrancar, porque el arranque es justo el momento
posterior a un reinicio.

**Decisión: Redis con persistencia y volumen.** Sin ella, un reinicio vacía
la cola. El barrido lo recoge, pero es mejor no perder los trabajos que
depender de que alguien los vuelva a lanzar.

**Decisión: `clock_timestamp()` y no `now()` en los valores por defecto.**
`now()` en Postgres devuelve la hora de **inicio de la transacción**, así que
dos filas insertadas en la misma transacción comparten marca al
milisegundo. Eso deja indeterminado el orden «la más reciente», que es justo
lo que decide qué extracción está vigente y en qué orden se listan las
ofertas. Se descubrió porque un test guardó dos extracciones seguidas y la
que salía como vigente era aleatoria. Queda un empate teórico si dos filas
caen en el mismo microsegundo, y para eso las consultas desempatan por `id`,
que es determinista aunque no signifique nada.

**Hallazgo: `alembic check` no compara valores por defecto salvo que se le
pida.** El cambio anterior no habría aparecido como deriva de esquema. Se
activa `compare_server_default`, que en este esquema no produce falsos
positivos.

**Decisión: los hijos de una extracción se cuelgan por la relación y no
fijando la clave ajena a mano.** Además de dejar que SQLAlchemy ordene los
INSERT, hace que el objeto devuelto traiga sus colecciones cargadas: leerlas
no dispara una consulta perezosa, que en código asíncrono no es una consulta
lenta sino una excepción.

**Decisión: la paginación del listado va por la captura ancla y no por
desplazamiento.** Un `OFFSET` se descuadra en cuanto entra una oferta nueva
mientras alguien mira la segunda página: repite o salta una fila.

**Decisión: la clave de deduplicación de empresas no toca los sufijos
societarios.** «Astillero Nube SL» y «Astillero Nube S.L.» quedan como dos
filas. Es el error que se prefiere: dos filas para una empresa se arreglan
fusionándolas, mientras que una fusión falsa mezcla dos empresas distintas y
no se deshace.

**Decisión: el worker escribe su latido cada quince segundos.** El valor por
defecto de arq es una hora, que para un `healthcheck` de Compose no sirve:
el latido estaría rancio casi siempre y el contenedor se marcaría enfermo
estando sano.

**Decisión: los tests de la tarea usan una fábrica de sesiones real y
limpian después.** La tarea commitea varias veces a propósito, así que no se
puede probar dentro de una transacción que se deshace; y probar la
estructura real de sus transacciones es parte de lo que interesa. Redis no
aparece en los tests: la tarea se invoca directamente, porque lo que aporta
arq es *cuándo* se reintenta, y eso no se prueba probando arq.

### Los endpoints y las pantallas

**Decisión: el endpoint declara en el tipo que solo acepta texto pegado.**
`source` es un `Literal` con un solo valor, no el enum entero: mandar
`source: "url"` da un 422 documentado en el OpenAPI en lugar de una
aceptación silenciosa de algo que no hay código para procesar. Los otros
cuatro canales existen en el contrato y en la columna, porque son Fase 4.

**Decisión: un texto ya capturado devuelve 200 sin encolar nada.** Sería
pagar dos veces por el mismo anuncio. Con `force_reextract` se encola
igualmente, que es lo mismo que hace el endpoint de reextracción.

**Hallazgo: la ingesta tenía una carrera, y la destapó el E2E en paralelo.**
Dos peticiones con el mismo texto competían entre la comprobación de
duplicado y el INSERT, y la perdedora se llevaba un 500 por violar la
unicidad de `raw_text_sha256`. Pasa de verdad con un doble clic en el botón.
Ahora se recoge la captura que ganó y se sigue como si se hubiera visto
desde el principio: la unicidad está en la base de datos justamente para que
esto no dependa de quién llegue antes. Tiene su test, forzando la carrera a
mano.

**Decisión: las listas de campos de la respuesta se derivan del esquema de
salida del modelo.** Añadir un campo al contrato lo hace aparecer en la
pantalla sin tocar la capa de vistas. Una lista escrita a mano se olvida, y
el campo nuevo se guardaría sin que nadie lo viera nunca.

**Decisión: el listado nombra al empleador final antes que a quien
publica.** De un vistazo interesa para quién se trabajaría, no qué
consultora publicó el anuncio.

**Decisión: la API arranca aunque Redis no conteste.** Seguir sirviendo
lecturas y `/api/health` es más útil que no levantar; lo único que se cae es
pedir una extracción nueva, y eso responde 503 con un mensaje que lo dice.
`/api/health` pasa a informar también del estado de la cola, y lo comprueba
de verdad con un `ping` en vez de mirar si el objeto existe: el pool se crea
al arrancar y Redis puede haberse caído después.

**Decisión: sin `REDIS_URL` no se intenta conectar.** Con una URL que no
responde, cada construcción de la aplicación en los tests pagaba los cinco
reintentos de arq: cuarenta segundos de harness por nada. Con
`ENV=production` la variable es obligatoria.

**Decisión: la pantalla enseña la evidencia con el mismo peso que el dato.**
La cita literal cuando consta, el razonamiento y la confianza cuando se
dedujo, «sin datos» cuando no aparece. Esa distinción es el proyecto entero,
así que no está escondida en un desplegable. Y se enseñan también las
correcciones que el código le hizo al modelo, que son la cuenta de cuántas
veces se salta las reglas.

**Decisión: un campo ausente no lleva marca de evidencia a la derecha.** Su
propio valor ya dice «sin datos» en el color de alerta, que es la
micro-decisión de `docs/APP_SCREENS.md`. Ponerlo dos veces multiplicaba el
ruido justo donde más filas ausentes hay —la compensación, que en Europa
casi nunca se publica— sin añadir nada. Se vio mirando una captura de
pantalla de la página real, no leyendo el código.

**Decisión: la página se refresca pidiéndose otra vez al servidor, no
sondeando la API desde el navegador.** Así el estado que se pinta y el que
ve el backend son el mismo, y no hay una segunda forma de leer una oferta
que pueda desincronizarse de la primera. El refresco se para solo cuando la
extracción termina.

**Decisión: el mínimo de longitud se comprueba también en el frontend.** No
es desconfianza del backend, que sigue mandando: es idioma. El 422 de la API
trae el mensaje de pydantic en inglés, y quien acaba de pegar un anuncio no
tiene por qué leer eso.

**Decisión: las etiquetas de los campos viven en el frontend.** Cómo se
llama una columna en pantalla es presentación, y no tiene por qué viajar
traducida en cada respuesta. Un campo sin etiqueta se pinta con su nombre
técnico: feo, pero no lo oculta.

**Decisión: las migraciones son un paso aparte también en local y en CI.**
`make up` y el job de E2E las aplican explícitamente, igual que hace el
deploy. El contenedor no migra al arrancar, y sin tablas la ingesta falla,
que es justo lo que el E2E viene a comprobar.

### Desviaciones deliberadas

- **Aviso por Telegram del resultado del deploy** (`ARCHITECTURE.md` §11):
  fuera. No hay bot todavía, es Fase 3.
- **El rollback no revierte migraciones.** Vuelve al tag de imagen anterior,
  pero no hace `alembic downgrade`: revertir un esquema a ciegas puede
  perder datos. La disciplina correcta —migraciones compatibles hacia
  atrás— se mantiene desde la primera tabla de M1. Anotado en
  `docs/deployment.md`.
- **shadcn/ui, TanStack, Motion, Sonner, cmdk, Recharts, Zod y
  `openapi-typescript`** (`ARCHITECTURE.md` §8): fuera de M0. Ninguno tiene
  nada que hacer en una página de estado, y añadirlos ahora sería fijar
  decisiones de composición sin una pantalla real que las justifique.
- **`@types/node` en `^24`, no en el `^20` que puso `create-next-app`.**
  Vitest 5 exige `>=22`; se alinea con el Node 24 de la imagen.
- **`services/web/AGENTS.md` se commitea tal cual.** Lo escribe y lo repone
  `next dev` en cada arranque; borrarlo solo deja el árbol sucio. Se le
  añade, fuera de los marcadores que Next reescribe, una nota de que las
  reglas del repositorio son las de la raíz.

### Verificación en esta máquina, 2026-09-03

- `make check`: `cv_builder` 22 tests, `api` 14 tests, `web` 5 tests; ruff,
  `mypy --strict`, eslint y `tsc --noEmit` limpios en los tres.
- `docker compose up --build`: las cuatro imágenes construyen para arm64 y
  los cuatro servicios levantan sanos.
- A través de Caddy en `http://localhost:8080`: `/api/health` da
  `{"status":"ok","database":"ok"}`, `/api/auth/me` devuelve el usuario del
  bypass, y la página trae ese estado ya en el HTML inicial.
- Camino degradado: con `postgres` parado, `/api/health` responde 503 con
  `database: unreachable` y la página lo pinta con `▲` en vez de romperse.
- `alembic upgrade head` y `alembic current` dentro del contenedor: no-op
  correcto, sin migraciones.
- `e2e`: los 3 tests de Playwright pasan contra el stack levantado.
- YAML de los dos workflows parseado, y los bloques `run` del deploy
  comprobados con `bash -n`, incluida la terminación de los heredocs.

**Sin verificar, y no se puede desde aquí:** el deploy real. La VM de
Oracle, el dominio y el cliente OAuth de Google no existen todavía; lo que
hay que provisionar está en `docs/deployment.md`, y `deploy.yml` falla con
un mensaje claro mientras falten los secretos.

## 2026-09-03 — M1, ingesta y extracción (en curso)

La rebanada no está cerrada: falta la persistencia, la cola, los endpoints y
la pantalla. Se documenta lo decidido hasta aquí porque el porqué de una
decisión se olvida antes que el código que la implementa.

El alcance es `POST /api/offers/ingest` con **solo texto pegado** —los otros
cuatro canales del contrato son Fase 4— produciendo las capas `capture` y
`extraction`. El scoring es M2 y la entrega del PDF es M3.

### El esquema

**Decisión: la captura *es* la oferta; no hay tabla `offers` por encima.** El
contrato escribe `offer.posting_company_id`, lo que sugiere una entidad
estable de la que cuelgan las capas. Pero `employer_confidence` es una
inferencia del modelo: si viviera en una fila estable, reextraer con otro
`prompt_version` la sobrescribiría, y se rompería justo la inmutabilidad que
justifica separar las capas. Así que las referencias a empresa cuelgan de la
extracción, y la identidad estable de la oferta es la captura.

**Decisión: el valor de cada campo va en columna tipada y el sobre de
evidencia en un `jsonb` con la clave del campo.** Se descartaron dos
alternativas. Una columna por cada parte del sobre (`status`,
`source_quote`, `reasoning`, `confidence`) serían casi noventa columnas. Un
único `payload` jsonb perdería los tipos, los CHECK y la capacidad de que M2
puntúe leyendo SQL. Un campo `absent` es columna `NULL` más
`evidence[campo].status == "absent"`.

**Decisión: se descartó la tabla EAV, y conviene anotar por qué, porque era
tentadora.** Una tabla `extraction_fields` con una fila por campo permitiría
imponer la regla transversal del contrato —todo campo lleva evidencia— con
un solo CHECK, válido para todos los campos presentes y futuros, incluidos
los que traigan M2 y la Fase 4. Se descartó porque el encargo dice
explícitamente que la validación va **en Python**, y EAV se paga con tipos
perdidos, un join para leer una oferta y un vocabulario de campos que la
base de datos no conoce. La regla acabó impuesta en `rules.py`, y en la base
de datos solo lo que una columna tipada puede expresar barato.

**Decisión: `companies` solo identifica.** Sin `sector`, `size` ni
`funding_stage`, que el contrato pide con su evidencia cada uno: de un texto
pegado no salen honestamente, y rellenarlos desde el anuncio sería
exactamente el `absent` con estimación que el contrato prohíbe. Corolario
coherente: lo que el modelo *afirme* sobre una empresa vive en la
extracción, que es donde vive la evidencia; `companies` guarda nombre y
clave de deduplicación.

**Decisión: `match`, `evidence_ref` y `cv_action` existen como columnas pero
quedan en NULL en todo M1.** Cruzar un requisito contra el banco de
evidencias exige leer el repositorio privado, y ese clon es M3. `NULL`
significa «sin evaluar», que **no** es lo mismo que `no_evidence`,
«evaluado y no se ha encontrado nada»: confundirlos haría que M2 se saltara
los requisitos que nadie ha mirado todavía. El CHECK y la regla en Python
entran ya, con tests, para que M2 herede una regla que lleva tiempo
aguantando peso en lugar de escribirla con prisa.

**Decisión: la inmutabilidad la impone un trigger `BEFORE UPDATE`, no una
convención.** Cinco líneas en la migración cubren las dos capas del
contrato y sus hijas. `job_runs` y `llm_calls` no lo llevan: un job cambia
de estado y no es una capa del contrato. `DELETE` sigue permitido —inmutable
no es imborrable, y un texto pegado por error se tira— y arrastra en
cascada. El DDL no queda afectado, así que añadir columnas sigue siendo
libre; lo que queda bloqueado es rellenarlas, y un backfill futuro tendrá
que quitar y reponer el trigger en su propia migración, que es la decisión
explícita que se quiere forzar.

**Decisión: los vocabularios cerrados son VARCHAR con CHECK, no enums
nativos de Postgres.** Ampliar un enum nativo exige `ALTER TYPE ... ADD
VALUE`, que no se puede usar en la misma transacción que lo necesita y no
tiene inverso; cambiar una constraint en una migración sí es reversible, y
la reversibilidad se comprueba en CI porque el rollback del deploy no
revierte esquema.

**Hallazgo que corrigió un comentario falso: `create_constraint` vale `False`
por defecto desde SQLAlchemy 1.4.** Las dieciocho columnas de vocabulario
eran VARCHAR pelados que aceptaban cualquier cadena. Se descubrió metiendo
un canal inventado con `psql`, no leyendo el código: el comentario decía que
había una red debajo y no la había. Queda explícito y comentado.

**Consecuencia: esos CHECK quedan fuera de la comparación de Alembic.**
Alembic los excluye del lado del metadata —los considera gestionados por el
tipo de la columna— pero sí los reflecta de la base de datos, así que
`--autogenerate` proponía borrar los dieciocho en cada revisión y
`alembic check` no podía estar limpio. Se filtran con `include_name`. El
precio del filtro es que ampliar un vocabulario deja de aparecer como deriva
de esquema, y lo paga un test que compara cada CHECK real contra su
`StrEnum`: es más preciso que autogenerate, porque mira los valores y no
solo la existencia de la constraint.

**Decisión: sin `unique(capture_id, prompt_version)`.** Reextraer tras un
fallo con la misma versión tiene que poder crear fila. La extracción vigente
es la última por `(extracted_at, id)`; no hay flag `is_current`, porque un
flag mutable en una tabla inmutable es una contradicción que se paga tarde.
Si algún día hay que fijar una versión concreta, el cambio aditivo es un
`current_extraction_id` en la captura.

**Decisión: `raw_text_sha256` es único.** El contrato lo pide para *detectar*
reingestas; hacerlo único además impide pagar dos veces por el mismo texto,
y deja la invariante en la base de datos en vez de en la buena voluntad del
endpoint. El endpoint devolverá la captura existente en lugar de un error.

**Decisión: `job_runs` y `llm_calls` son dos tablas y no una.**
`ARCHITECTURE.md` §5 pide dos cosas distintas —ejecuciones de jobs y coste
de LLM— y en M2 un job de scoring hará más de una llamada al modelo. El
precio es un join. Y no hay FK circular entre `job_runs` y
`offer_extractions`: el camino de vuelta es un índice único en
`offer_extractions.job_run_id`, que además impone que un job produzca como
mucho una extracción.

**Decisión: la convención de nombres del `MetaData` entra antes de la primera
migración.** Después habría sido tarde: los nombres autogenerados dependen
del backend, y un `downgrade` que borra una constraint por su nombre se
vuelve frágil. En CI se ejecuta el ciclo completo
`upgrade` → `check` → `downgrade base` → `upgrade`, que es donde se
comprueba la reversibilidad que el rollback del deploy no cubre.

**Decisión: la clave primaria lleva las dos formas de generar el UUID**,
`default` de Python y `server_default` con `gen_random_uuid()`. Sin la
segunda, cualquier INSERT que no venga del ORM falla por `id` nulo, y eso
incluye una migración de datos y una sesión de `psql`. Se descubrió porque
cuatro pruebas del primer sondeo del esquema «pasaban» por el motivo
equivocado.

**Decisión: un tercer módulo, `futuro_api/models.py`, reúne las tablas.** Las
dos mitades se referencian mutuamente —`offer_extractions.job_run_id` apunta
a `job_runs`, y `job_runs.capture_id` a `offer_captures`— así que ninguno de
los dos módulos puede importar al otro sin un ciclo. Importar solo una mitad
hace que SQLAlchemy no encuentre la tabla de la otra al configurar los
mapeos, y el error sale tarde: no al importar, sino la primera vez que
alguien usa el ORM.

### El código que valida

**Decisión: tres clases de respuesta a un incumplimiento, y no una.**
Tratarlos igual sería un error en las dos direcciones —rechazar todo por un
importe negativo, o guardar una cita inventada como si fuera una cita—.

1. **Rechazo** (`ExtractionRejected`, no se guarda nada) cuando no hay
   degradación honesta: `published` sin cita, `inferred` sin razonamiento o
   sin confianza, `absent` con un valor rellenado, evidencia sin valor, un
   empleador final sin confianza, una anomalía que apunta a un requisito que
   no existe.
2. **Degradación al máximo que el contrato permite**: `active_verified` sin
   comprobación pasa a `unverifiable`; `meets` sin `evidence_ref` pasa a
   `partial`.
3. **Descarte del campo a `absent`** cuando la afirmación no se sostiene
   pero el resto de la extracción sí: una cita que no está en el anuncio, un
   importe negativo, una moneda que no es un código ISO.

Todo lo corregido se acumula en `corrections`, que se guarda con la
extracción y se pinta en pantalla. No es un log: es la cuenta de cuántas
veces el modelo se salta las reglas, y es el dato que dice si hay que
cambiar el prompt o el modelo.

**Decisión: las infracciones se juntan antes de lanzar, no se para en la
primera.** Si hay que cambiar el prompt, conviene verlas todas de una vez en
lugar de descubrirlas de una en una a base de reintentos que se pagan.

**Decisión: cada `source_quote` se verifica contra `raw_text`.** Es la
comprobación más fuerte disponible y también la más barata: el modelo no
puede fabricar una cita. La comparación normaliza el ruido de transcripción
—espacios, saltos de línea, comillas y guiones tipográficos, mayúsculas—
porque un modelo cambia eso al copiar sin estar inventando nada, y no
perdona nada más. Una cita que no aparece deja el campo en `absent`, que es
lo único honesto que se puede afirmar cuando la prueba no existe.

**Decisión: lo que el esquema de salida del modelo *no* tiene.** No están
`status_checked_at`, ni `match`, ni `evidence_ref`, ni `cv_action`. Eso hace
`active_verified` inalcanzable **por construcción** y no por validación, y
hace imposible que el modelo afirme que el perfil cumple un requisito. No
poder decirlo es más fuerte que decirlo y que el código lo tache.

**Decisión: en M1 el código nunca acepta `active_verified` de un texto
pegado.** Que el anuncio se describa como activo no es una comprobación, y
no hay URL que consultar. La regla queda escrita y probada, pero el valor
solo será alcanzable cuando exista el canal URL (Fase 4).

**Decisión: las anomalías apuntan al requisito por índice, no por texto.** Un
índice se puede comprobar —fuera de rango es una respuesta inventada— y
cruzar cadenas es adivinar. Descartar un requisito renumera los siguientes,
así que el índice del modelo se traduce a la posición final.

**Decisión: la versión del prompt va atada a su texto por una huella
registrada en el test.** `offer_extractions` está versionada por
`prompt_version`, así que dos filas de la misma versión tienen que haber
salido del mismo prompt. Editar el texto rompe el harness; arreglarlo obliga
a subir la versión y registrar la huella nueva, que son los dos actos
conscientes que se quieren forzar. Las versiones antiguas se quedan en la
tabla del test: son las que explican qué produjo cada fila vieja.

**Decisión: el esquema de salida se comprueba contra las condiciones del modo
estricto en un test.** *Structured outputs* rechaza con un 400 lo que no
cumple —propiedades no obligatorias, `additionalProperties` ausente,
`minLength`— y sin ese test el fallo aparecería en la primera llamada real,
con la clave puesta y el gasto hecho.

**Decisión: una horquilla salarial invertida descarta los dos extremos.**
Intercambiarlos es adivinar cuál está mal, y una banda invertida que se
cuele envenena el scoring de M2 en silencio, que es peor que no tener banda.

**Decisión: un requisito marcado como anómalo sin explicación se registra, no
se reetiqueta.** La señal de que algo va mal en el anuncio le sirve al filtro
automático de M2 aunque el modelo no haya dicho por qué.

**Decisión: dos vocabularios se cierran aquí porque el contrato los nombra
sin fijar valores**: `comp_period` (`year`, `month`, `day`, `hour`,
`unclear`) y `comp_territorial_adjustment` (`localised`, `not_localised`,
`unclear`). Un campo abierto no se puede validar. Queda pendiente
reflejarlo en el contrato del repositorio privado, donde desde aquí no se
escribe.

**Decisión: `experience_years_required` se lee como el mínimo.** Si el
anuncio pide «3-5 años», el requisito es 3. Lo dice el prompt y lo repite un
comentario en el modelo, porque es la clase de decisión que alguien deshace
sin darse cuenta.

### El módulo de LLM

**Decisión: aislado quiere decir dos cosas concretas.** Que nada de `llm/`
sabe qué es una oferta —quien llama trae su prompt y su esquema, y
`offers/extraction.py` es la única costura— y que `llm/openai_client.py` es
el único fichero del repositorio que importa el SDK. Cambiar de proveedor es
escribir otro cliente que cumpla el protocolo `LlmClient`.

**Decisión: el coste viaja con la respuesta, no se calcula aparte.** Toda
llamada devuelve tokens, precio, versión de la tarifa y latencia. Un coste
que hay que acordarse de registrar es un coste que no se registra.

**Decisión: un modelo que no esté en la tabla de tarifas no arranca.**
`Settings` lo rechaza en el arranque, no en el primer trabajo encolado.
Antes eso que registrar un coste que nadie sabe calcular: es la misma
disciplina de no rellenar un hueco con una estimación, aplicada al dinero.
Se guardan los tokens, el coste y `PRICING_VERSION`, así que un precio mal
copiado se recalcula sin haber perdido el dato —la propiedad que hace
recalculable la capa `assessment`, aplicada aquí.

**Hallazgo fijado por un test: los tokens cacheados van dentro de
`input_tokens`, no aparte.** Tratarlos como un añadido facturaría la parte
cacheada dos veces, un factor de once en el caso extremo. No se ve mirando
el código, así que hay un test que lo fija.

**Decisión: el modelo por defecto es `gpt-5.6-terra`.** Precios consultados
en la página oficial de OpenAI el 2026-09-03, no de memoria; los
agregadores daban otros. Un anuncio sale por unos $0,034, que es el ~1 €/mes
que `ARCHITECTURE.md` §13 presupuesta. Esta tarea castiga al modelo barato
justo donde duele —la cita literal—, y cada cita inventada la caza la
verificación y cuesta un campo, así que ahorrar en el modelo se paga en
datos perdidos y no en dinero. `sol` y `luna` están en la tabla para que
cambiar sea una línea de `.env`.

**Decisión: el cliente simulado vive en el código de la aplicación, no en los
tests.** `LLM_PROVIDER=stub` es una configuración legítima en local: el CI no
tiene clave y no debería tenerla, el e2e tiene que ser determinista, y
desarrollar la pantalla a base de llamadas reales se paga en cada recarga.
En producción no arranca, con el mismo patrón que `DEV_AUTH_BYPASS`.

**Decisión: la respuesta simulada saca sus citas del propio texto pegado.** Es
lo que la convierte de comodidad en herramienta: la verificación de citas se
ejecuta de verdad y pasa con cualquier anuncio, así que el camino real se
recorre en local. Con citas escritas a mano, cualquier texto distinto del de
los tests dejaría todos los campos en `absent`. Rellena poco a propósito, y
su razonamiento dice literalmente que es simulada, que es lo que se ve en la
pantalla.

**Decisión: el valor por defecto de `LLM_PROVIDER` es `stub`.** Es lo que hace
que un clon nuevo levante con `make up` y pase `make check` sin clave. No es
un riesgo de producción porque `ENV=production` lo rechaza, y `llm_stubbed`
exige además `env == "development"`, así que la propiedad que decide qué
cliente se construye no depende solo de la variable.

### Desviaciones deliberadas

- **Sin tests del cliente real de OpenAI.** Lo único que hace es traducir
  entre el SDK y `LlmResult`; probarlo exigiría o una clave en el CI o un
  doble del SDK que se parecería más al SDK que a la realidad. Está probado
  todo lo que decide algo: la aritmética del coste, la puerta del modelo sin
  tarifa, y que el stub recorra el camino real de validación.
- **`redis` y `worker` no entran en el compose hasta que haya una tarea que
  ejecutar.** Meter un servicio que no hace nada es lo que M0 evitó
  explícitamente con estos dos mismos servicios.
- **Que un `evidence_ref` resuelva de verdad no se puede comprobar.** Hasta
  que exista el clon del repositorio privado (M3) solo se puede exigir
  presencia, y en M1 ni eso, porque el campo no se rellena.
- **Si el proveedor no devuelve consumo, la extracción se conserva y el coste
  se registra a cero, con un aviso en el log.** La llamada ya está pagada, y
  tirar una respuesta buena por no poder contabilizarla sería gastar el
  dinero dos veces. Queda el identificador de la respuesta para cuadrarlo
  contra el panel del proveedor.
- **Una cita de menos de tres caracteres se rechaza, y no hay más control de
  longitud.** Tres deja pasar `SQL` o `C#`, que son citas legítimas de un
  requisito de tecnología. Una cita corta es evidencia débil, pero no es una
  invención, y este módulo no distingue fuerza de evidencia: distingue
  verdad de mentira.
- **El worker no se prueba arrancado.** Lo que se ejecuta en los tests es la
  tarea, no arq. Que el worker arranque, coja trabajos de Redis y los
  ejecute se comprobó a mano con el stack levantado, y lo cubrirá el E2E.
- **El listado no filtra ni ordena.** Eso es la pantalla Pipeline, que no es
  esta rebanada. El listado existe solo para que la pantalla de una oferta
  sea alcanzable después de recargar.
- **La pantalla «Capturar» no tiene los pasos de extracción en vivo** que
  describe `docs/APP_SCREENS.md`. Es un área de texto y un botón. Los pasos
  en vivo tienen sentido cuando haya más de un paso que enseñar; de momento
  la espera se ve en la pantalla de la oferta, que se refresca sola.
- **La pantalla de la oferta no tiene la composición ponderada.** El ancho
  de cada barra es el peso de la dimensión en el modelo de scoring, así que
  necesita el scoring: es M2.
- **El listado no es la pantalla Pipeline.** Ni tabla densa, ni mapa valor ×
  probabilidad, ni kanban: eso también necesita el scoring. Es una lista
  para que una oferta siga siendo alcanzable después de recargar.
- **Siguen fuera shadcn/ui, TanStack, Motion, Sonner, cmdk, Recharts, Zod y
  `openapi-typescript`.** Los tipos del cliente se escriben a mano, que para
  cinco respuestas es más barato que montar la generación desde el OpenAPI.
  Cuando el número de endpoints crezca, esa decisión cambia.

### Verificación en esta máquina, 2026-09-04

- `make check`: 148 tests de la API y 10 del frontend; ruff, `ruff format`,
  `mypy --strict`, eslint y `tsc --noEmit` limpios.
- `make migrate-check`: `upgrade`, `check`, `downgrade base` y `upgrade`
  otra vez, sin deriva.
- `make up`: los seis servicios de `ARCHITECTURE.md` §4 sanos por primera
  vez, incluidos `redis` y `worker`.
- `make e2e`: los 6 tests de Playwright en verde, incluido el recorrido
  entero —pegar, extraer, ver— contra el stack levantado.
- Una oferta inventada encolada desde la API y procesada por el worker, con
  sus requisitos y su coste en la base de datos.
- La pantalla de la oferta revisada en una captura real, no solo por sus
  tests.

**Sin verificar, y no se puede desde aquí:** una extracción con el modelo de
verdad. Todo lo anterior corre con `LLM_PROVIDER=stub`, que es lo que
permite que el harness y el E2E sean deterministas y gratis. La primera
llamada real a OpenAI la hace Pablo cuando quiera, con su clave y su
presupuesto puestos.

## 2026-09-04 — M2, scoring y recomendación de variante (en curso)

El principio de esta rebanada es distinto del de M1 y conviene tenerlo
delante al leer lo que sigue: en la extracción **el LLM elegía y citaba**;
aquí **el LLM juzga y el código calcula**. El modelo pone la nota de cada
dimensión, la cita que la sostiene y el motivo; la media ponderada, la
renormalización, la cobertura, el cubo de cartera y el nivel de esfuerzo
salen de `assessment/scoring.py`, que es una función pura y no ve al modelo.

Se documenta a medida que avanza, no al cerrar: el porqué de una decisión se
olvida antes que el código que la implementa.

### La frontera con el repositorio privado

**Decisión: se monta la frontera ahora y el clon de git se queda en M3.** El
scoring necesita leer del repositorio privado `Futuro`, que era el primer
dato de ahí que la aplicación necesita, y el clon de solo lectura estaba
planificado para M3. Se descartó adelantarlo por un motivo concreto: la
deploy key es un secreto de GitHub y un montaje en la VM, así que adelantar
el clon obligaba a tocar `docs/deployment.md` y el workflow de deploy, que
están en manos de otra sesión en paralelo. Lo que se monta es
`futuro_api/data_repo/`, cuya única entrada es un directorio
(`DATA_REPO_PATH`). Hoy ese directorio lo pone un *bind mount* de solo
lectura; en M3 lo pondrá el clon, y no cambia una línea de arriba.

**Decisión: se descartó copiar el modelo de scoring a este repositorio.** Se
anota porque era la opción más rápida y es la que hay que no volver a
proponer: `baseline_madrid` son el bruto, el neto y la tasa de ahorro de
Pablo. Es exactamente el dato que el primer principio de `AGENTS.md`
prohíbe.

**Decisión: falla cerrado y ruidoso.** Sin directorio, o con un YAML que no
cumple la forma, el trabajo de puntuación queda `failed` con el motivo, y la
pantalla lo enseña. No hay pesos por defecto en ninguna parte, así que no
existe el camino en el que se puntúa con un modelo de scoring inventado. El
repositorio de datos **no** es obligatorio con `ENV=production`, y eso sí es
una decisión: hasta M3 no hay clon, y negarse a arrancar dejaría la
aplicación entera caída por una función que todavía no puede funcionar.

**Decisión: cada fila guarda el `sha256` del fichero que leyó.**
`config/scoring_model.yaml` declara `version: 1` y el propio contrato cuenta
que el modelo cambió dos veces el 2026-08-13, así que fiarse del número
declarado es fiarse de que alguien se acuerde de subirlo. El hash es gratis y
no se olvida. Lo mismo con `variants_guide_sha256`.

**Decisión: el cargador no cachea.** Se releen los seis YAML en cada trabajo.
Al lado de una llamada al modelo el coste es irrelevante, y en local tiene la
propiedad que se quiere: editas un peso y el siguiente trabajo ya lo usa.

**Corrección de un supuesto del diseño: no todo el vocabulario del
repositorio de datos puede ser libre.** La idea de partida era que cualquier
vocabulario que viva en el YAML fuese `text` sin CHECK, validado en Python:
una migración no debe ir detrás de un fichero que se edita a mano. Eso vale
para los nombres de dimensión, los de filtro y los identificadores de
variante, que el código transporta sin decidir nada con ellos. **No vale**
para las bandas de probabilidad, los cubos de cartera y los niveles de
esfuerzo: para calcular el cubo hay que preguntar «¿es esta banda `high`?»,
así que renombrar `high` en el YAML no rompería una constraint, cambiaría en
silencio el resultado de una comparación y todas las ofertas caerían en otro
cubo. Esos tres son vocabulario de código con su CHECK, y el cargador
comprueba al arrancar que el YAML declara exactamente esos nombres —en las
dos direcciones: uno que falta deja un cubo inalcanzable y uno de más es una
regla que el código no sabe calcular—. Lo mismo con la escala 0-5, que está
escrita en un CHECK.

**Decisión: los predicados del cubo y del esfuerzo van escritos a mano, con
su fecha, y no leídos del YAML.** No es pereza: `portfolio_assignment` y
`output.effort_tier` no expresan sus reglas en forma legible por máquina.
`realistic: probabilidad high y valor >= 3.0` es prosa. Lo que sí es legible
—pesos, anclas, escala, nombres, `minimum_coverage`, `evaluation_order`— se
lee del YAML y no se repite. Los dos umbrales (3,0 y 4,0) están copiados a
mano en `assessment/scoring.py` con la fecha de lectura, que es exactamente
lo que hace `llm/cost.py` con la tabla de tarifas del proveedor y por la
misma razón: la fuente es prosa para humanos. Las tres defensas también son
las mismas: el cargador exige que los nombres coincidan, cada fila guarda el
hash del YAML, y repuntuar no cuesta una llamada. Cuando esos dos bloques
pasen a forma legible por máquina en el repositorio privado, estos umbrales
se borran.

**Decisión: el repositorio de datos sintético vive en
`services/api/tests/fixtures/data_repo/` y es distinto del real en todo lo
que el código no debe dar por supuesto.** Cuatro dimensiones y no seis, con
otros nombres y otros pesos; tres filtros y no cuatro; `minimum_coverage` en
0,60 y no en 0,50; cuatro variantes y no cinco, con identificadores
inventados. Si algún día un test pasa por casualidad porque alguien escribió
en el código el nombre de una dimensión real, ahí se cae. Dos excepciones
deliberadas: los nombres de banda, cubo y nivel son los mismos, porque son
vocabulario de código; y `objectives.role_families.core` incluye dos valores
del `RoleFamily` de M1, porque si no ninguna oferta caería nunca dentro del
objetivo y la rama que no asigna `experimental` no se probaría nunca.

**Decisión: `.env.example` apunta al repositorio sintético.** Es lo que hace
que un clon nuevo levante con `make up` y recorra el camino entero —pegar,
extraer, puntuar, ver— sin tener el repositorio privado delante ni gastar
nada. El `.env` de Pablo apunta al real.

### Dónde va el cruce de requisitos, y por qué no donde el contrato lo dibuja

**Hallazgo que decidió el diseño: `offer_requirements` lleva el trigger de
inmutabilidad desde M1.** Está en `_IMMUTABLE_TABLES` de la migración 0001,
así que los campos `match`, `evidence_ref` y `cv_action` que M1 dejó en NULL
**no se pueden rellenar después**: un `UPDATE` no pasa. Eso descarta la
lectura obvia del encargo —«que M2 empiece a rellenar esos campos»— y deja
tres caminos.

**Decisión: el cruce vive en la capa `assessment`, en
`offer_requirement_matches`.** Las columnas de `offer_requirements` se quedan
en NULL para siempre, y NULL sigue significando «sin evaluar». Las dos
alternativas se descartaron con motivo:

- **Rellenarlas dentro del trabajo de extracción**, en el INSERT. Obligaría a
  que la extracción leyera el banco de evidencias, metiendo un juicio sobre
  el perfil en la capa que dice «esto leí en el anuncio». Y lo peor: cuando
  el banco de evidencias cambie —que es literalmente la Fase 2, perfil
  editable— volver a cruzar exigiría reextraer y pagar el LLM otra vez, que
  es justo lo que separar las capas evita.
- **Quitar y reponer el trigger para un backfill.** M1 dejó eso previsto para
  una migración, no para el runtime de cada oferta.

Es una desviación deliberada del contrato, que dibuja `match` dentro de
`requirements[]` en la sección de `extraction`. Se toma porque la propia
regla del contrato —«`assessment` se recalcula sin volver a llamar al
LLM»— exige que un cruce contra un banco que cambia no viva en una capa
inmutable. Queda pendiente reflejarlo en `OFFER_DATA_CONTRACT.md` del
repositorio privado, donde desde aquí no se escribe.

**Decisión: `evidence_ref` tiene que resolver, no solo estar.**
`rules.enforce_match_rule`, escrita y probada en M1 sin datos, se llama ahora
con datos de verdad, y con la comprobación fuerte que en M1 no se podía
hacer: la referencia tiene que apuntar a un `bullet_id` que exista en
`cv/content/professional_bullet_bank.yaml`, esté `verified` y sea divulgable
(`cv_usage: eligible_with_internal_policy_check`). Los dos estados, no uno:
el primero dice que el contenido está comprobado y el segundo que se puede
divulgar. Una referencia que no resuelve es el parecido de palabras que el
contrato prohíbe, con la forma de un identificador.

**Decisión: solo contra el banco de bullets, no contra
`profile/evidence_bank.md`.** El primero tiene identificadores y estados, así
que una referencia se puede comprobar; el segundo es prosa y casi todo está
en `candidate`. Una referencia a un párrafo no se puede verificar, y una
referencia que no se puede verificar es la que el contrato prohíbe.

**Decisión: `cv_action` se queda fuera de M2.** La columna existe y se queda
nula. `ARCHITECTURE.md` §7 descarta explícitamente la adaptación fina por
vacante —el LLM elige entre cinco PDF, no reordena bullets— así que hoy nadie
consumiría `include`/`prioritise`/`omit`, y un campo que nadie lee se llena
mal sin que nadie se entere.

### El esquema de la capa `assessment`

**Decisión: el assessment cuelga de la extracción, no de la captura.** Es la
conclusión sobre una lectura concreta del anuncio; si se reextrae con otro
prompt, seguir enseñando la conclusión anterior como vigente sería mentir. El
vigente es el último por `(assessed_at, id)` de la extracción vigente: el
mismo patrón que M1, y sin marca mutable de «vigente» por el mismo motivo.
Sin `unique(extraction_id, scoring_model_version)`, también por lo mismo:
repuntuar tras un fallo con la misma versión tiene que poder crear fila.

**Decisión: append-only, con el trigger de inmutabilidad de las otras dos
capas.** «Recalculable» significa insertar una fila nueva, no editar la
vieja. Sin el trigger, alguien arregla una nota en sitio y la promesa que
justifica guardar `scoring_model_version` —que dos ofertas puntuadas con
modelos distintos se noten— muere en silencio.

**Decisión: las dimensiones y los filtros son tablas hijas, no columnas.**
Seis columnas tipadas serían duplicar en el esquema la lista de dimensiones,
que vive en el YAML. No es la EAV que M1 descartó: la forma es fija y
uniforme, no un vocabulario de campos que la base de datos desconoce. El
precio de un join se cobra con lo que un `jsonb` no daría: los CHECK que
imponen la regla central del contrato y poder preguntar en SQL cuánto puntúa
de media una dimensión en toda la cartera.

**Decisión: la fila de dimensión guarda el `weight` y el `anchor` que se le
aplicaron.** Es lo que hace reproducible la composición ponderada de la
pantalla: la barra de una oferta puntuada en marzo se dibuja con el peso que
produjo su nota, no con el de hoy. Y significa que la API no necesita leer el
repositorio de datos para pintar, así que el repositorio de datos es una
dependencia **solo del worker**.

**Decisión: «sin puntuar» es la propia fila con la nota vacía.** No hay una
lista `unscored_dimensions` aparte que pueda contradecir a las notas. Dos
CHECK lo sostienen: `score IS NULL OR citation IS NOT NULL` —la regla central
del contrato, en la base de datos— y `(score IS NULL) = (unscored_reason IS
NOT NULL)`.

**Decisión: la recomendación de variante es su propia tabla.** La propiedad
que define esta capa es que se recalcula sin volver a llamar al modelo, y la
elección de variante **no** se puede recalcular sin llamarlo. Como tres
columnas del assessment, cada repuntuación tendría que o pagar otra llamada o
arrastrar la elección anterior, y la propiedad dejaría de ser cierta.
Separada, repuntuar el histórico no toca ninguna variante elegida, y en M3 la
confirmación manual de Pablo no la borra un recálculo.

**Decisión: `source` (`llm` / `recomputed`) con tres CHECK que la atan.** Un
recálculo no tiene `job_run_id` y sí `derived_from_id`; un assessment del
modelo, al contrario, y además declara `prompt_version` y `model`. Es la
invariante que hace comprobable la repuntuación: si algún día alguien
«recalcula» llamando al LLM, el esquema no le deja guardarlo.

**Decisión: un cubo que falta lleva siempre su motivo** (`portfolio_bucket IS
NOT NULL OR portfolio_note IS NOT NULL`). Es lo que hace que un hueco en
pantalla se pueda leer en vez de parecer un fallo de la aplicación.

### La migración 0002

**Decisión: la única cosa que cambia de 0001 es el vocabulario de
`job_runs.kind`.** Todo lo demás son tablas nuevas, así que es compatible
hacia atrás y la versión anterior de la aplicación sigue funcionando contra
este esquema, que es lo que exige el rollback del deploy. Ese CHECK va
escrito a mano porque el filtro `include_name` lo excluye de la comparación
de Alembic; lo vigila el test que compara los valores del CHECK real contra
el `StrEnum`.

**Hallazgo: el `downgrade` no es simétrico y no puede serlo.** Estrechar el
vocabulario de `job_runs.kind` obliga a borrar antes las filas de los
trabajos de puntuación, porque si no violarían el CHECK que se repone. Es
pérdida de datos en un `downgrade`, y es aceptable porque lo que esas filas
registran apunta a tablas que ese mismo `downgrade` está borrando. Queda
comentado en la migración: es el tipo de cosa que alguien «arregla»
quitándole el DELETE y descubre que la migración ya no baja.

### El reparto entre el modelo y el código

**Decisión: lo que el código calcula no está en el esquema de salida del
modelo.** El encargo decía «el código NUNCA acepta un `value_score` que
venga calculado por el modelo, aunque lo mande». La forma fuerte de esa
regla no es tacharlo al validar: es que no exista el campo.
`assessment/schemas.py` no tiene `value_score`, ni `coverage`, ni
`portfolio_bucket`, ni `effort_tier`, ni `unscored_dimensions`, ni el peso
de la dimensión. Con `extra="forbid"`, una respuesta que los mande **no
parsea**, así que no hay ningún camino por el que lleguen. Es el mismo
patrón que hizo `active_verified` inalcanzable en M1: no poder decirlo es
más fuerte que decirlo y que el código lo tache. Hay un test que manda un
`value_score` a propósito y comprueba que la respuesta se cae.

**Decisión: el esquema pide una lista de dimensiones y no un campo por
dimensión.** Generar el modelo Pydantic desde el YAML cargado daría la forma
más fuerte todavía —el modelo no podría dejarse una dimensión sin
contestar—, y se descartó: el esquema de salida de una llamada dejaría de
ser legible en el repositorio, y no se podría revisar sin ejecutar nada. Lo
que se pierde se recupera en `rules.py`, que exige exactamente las
dimensiones cargadas y deja sin puntuar las que el modelo no devuelva.

**Decisión: una nota sin cita utilizable deja la dimensión sin puntuar, y no
se corrige la nota.** Cuatro formas de lo mismo, y las cuatro con test: sin
cita, con la cita vacía, con una cita más corta que tres caracteres, y con
una cita que no aparece en el anuncio. Una nota sin cita comprobable no es
una nota más baja: es una nota que no existe.

**Decisión: una nota fuera de escala se descarta y no se recorta.** Recortar
un 9 a un 5 sería inventarse una nota. El modelo dijo algo que no significa
nada en esta escala, y lo honesto es que la dimensión quede sin puntuar.

**Decisión: la verificación de citas es literalmente la misma función que la
de la extracción.** `assessment/rules.py` importa `normalise` y
`MIN_QUOTE_CHARS` de `offers/rules.py`. No es reutilización por ahorrar
código: «una cita se comprueba contra el anuncio» tiene que significar
exactamente lo mismo en las dos capas, y con dos implementaciones acabaría
no significándolo.

**Decisión: un filtro que decide sin cita comprobable pasa a `pending`,
nunca a `fail`.** Es la regla del YAML —«un filtro que no puede evaluarse
queda pending, nunca se supone superado»— y su simétrica, que no está
escrita pero se deduce: tampoco se supone incumplido. Y un filtro `pending`
no guarda cita: si algo del anuncio lo resolviera, no estaría pendiente.

**Decisión: tres casos de rechazo, y el resto son degradaciones.** Se
rechaza la respuesta entera cuando no hay degradación honesta: una banda de
probabilidad sin motivo (la columna es obligatoria, y al contrario que una
nota no se puede dejar «sin puntuar»), un juego de dimensiones en el que
ninguna es del modelo de scoring (es una respuesta a otra pregunta), y la
misma dimensión puntuada dos veces con notas distintas (elegir una sería
adivinar cuál quiso decir). Una lista de dimensiones **vacía**, en cambio,
sí se acepta: son cuatro dimensiones sin puntuar, que es una respuesta
pobre pero es una respuesta.

**Decisión: una variante que no existe rechaza la recomendación entera.** No
hay degradación honesta: elegir otra sería inventar. El test lo prueba con
`batimetria_profunda`, que está declarada en `cv_variants.yaml` y no tiene
carpeta, porque es el caso realista: el modelo la ve mencionada en la guía y
la elige.

**Decisión: `baseline_madrid` va en el prompt.** Es la primera vez que un
dato económico de Pablo sale hacia el proveedor: bruto anual, neto mensual y
ahorro de referencia. La alternativa —no mandarlo— deja la dimensión
`expected_net_savings`, que pesa 20 sobre 100, sin puntuar siempre, porque
las anclas están escritas en euros de ahorro contra esa referencia y sin
ella no hay nada contra lo que comparar. Se manda, y queda anotado aquí
porque es reversible: quitar un bloque del prompt es una línea.

**Consecuencia relacionada, y conviene saberla de antemano:** el prompt le
repite al modelo la prohibición de `missing_data.never` —no estimar sueldos,
impuestos ni coste de vida— y le dice explícitamente que si para comparar
tendría que estimarlos, deje la dimensión sin puntuar. Con eso, en la
mayoría de anuncios europeos sin salario publicado `expected_net_savings` y
`compensation_upside` quedarán sin puntuar y la cobertura rondará 0,65. Está
por encima del mínimo de 0,50, así que sí se emite puntuación, pero **ese
será el caso normal y no la excepción**.

### El prompt y el cliente simulado

**Decisión: dos prompts con su huella registrada, como en M1.** Con una
diferencia que hay que tener presente: la huella **no cubre** el contenido
del repositorio de datos. Las anclas, los filtros y la guía de variantes se
interpolan en el mensaje de usuario y cambian sin pasar por el código. Eso
no es un agujero en la disciplina: es la razón por la que cada fila guarda
`scoring_model_sha256` y `variants_guide_sha256`. La versión del prompt dice
qué se le pidió al modelo; el hash dice con qué material.

**Decisión: lo estable va delante del anuncio en el mensaje de usuario.** Por
la caché de prompt del proveedor, que cubre el prefijo. En una tarea que
manda el modelo de scoring entero en cada llamada eso es la diferencia entre
pagar el contexto una vez y pagarlo por oferta, y hay un test que fija el
orden de los bloques.

**Decisión: al modelo se le manda también la evidencia que *no* vale, con su
estado.** Mandar solo las utilizables parece más limpio y es peor: el modelo
no tendría forma de decir «hay algo parecido y no me sirve», y devolvería
`no_evidence` donde la respuesta honesta es `partial`.

**Decisión: el cliente simulado contesta leyendo del propio prompt qué se le
ha preguntado.** Las dimensiones, los filtros, las evidencias y los
requisitos los saca del mensaje que ha recibido, no del repositorio de
datos. La alternativa era que cargase el repositorio por su cuenta, y se
descartó por un motivo concreto: el cliente se construye una vez al arrancar
el worker y el cargador relee los YAML en cada trabajo, así que en cuanto
alguien editase un peso en local el stub estaría contestando sobre un modelo
de scoring distinto del que valida `rules.py`, y el resultado serían
dimensiones «desconocidas» en una pantalla sin ninguna pista de por qué. El
precio es que el formato del prompt pasa a ser una interfaz, y lo vigila un
test que compara lo que los parsers leen contra lo que el repositorio de
datos declara.

**Hallazgo: el primer parser del prompt se ataba a un nivel de encabezado y
devolvía listas vacías sin quejarse.** El prompt usa `#` para las secciones
grandes y `##` y `###` dentro; el parser solo miraba `##`, así que las
posiciones de requisito salían vacías y el stub no cruzaba nada. Lo destapó
una prueba de humo del camino entero antes de escribir un solo test, no
leyendo el código. Ahora el parser recorre el índice del documento por
niveles.

**Decisión: la respuesta simulada puntúa la mitad de las dimensiones.** Con
los dos modelos de scoring que existen —el real de seis y el sintético de
cuatro— eso deja la cobertura por encima del mínimo, así que en local se ve
el número grande; y deja dimensiones sin puntuar, así que también se ve el
hueco rayado. Los dos caminos de la pantalla se recorren en cada trabajo
simulado sin tener que provocarlos. Igual con los filtros: el primero se
decide con una cita del anuncio y el resto quedan pendientes.

**Decisión: la nota simulada es un 3 y no un 5.** Un stub que puntuara alto
haría que toda oferta pegada en local pareciera excelente.

### La cola

**Decisión: un solo tipo de trabajo nuevo, con dos llamadas al modelo.**
`offer_assessment` puntúa y elige variante. Es exactamente el caso que
`docs/decisions` de M1 anticipó al separar `job_runs` de `llm_calls`, y el
diseño aguantó: `job_runs` no ha ganado ninguna columna. Los dos propósitos
—`offer_scoring` y `cv_variant_choice`— son lo que permite mirar cuánto
cuesta cada mitad en vez de un total ciego.

**Decisión: el trabajo es atómico.** Si la elección de variante no se
sostiene, no se guarda tampoco el assessment. Guardar medio resultado
dejaría una oferta puntuada y sin variante que nadie distinguiría de una a
la que todavía le falta la variante, y el trabajo aparecería como fallido
habiendo escrito algo. Cuesta las dos llamadas, que es el mismo precio que
M1 aceptó al rechazar una extracción entera; y las dos quedan registradas
con su coste antes de validar, por lo mismo que en M1.

**Decisión: el repositorio de datos se carga antes de llamar al modelo.**
Descubrir que no está después de pagar dos llamadas sería tirar el dinero
por una comprobación que cuesta leer seis ficheros.

**Decisión: la extracción encadena la puntuación al terminar bien.** Es lo
que hace que el recorrido siga siendo de punta a punta —pegar, extraer,
puntuar, ver— sin un botón intermedio. Si el encolado falla, la extracción
**no** se cae: se queda sin puntuar, la pantalla lo dice y el botón de
puntuar sigue ahí. Perder una llamada ya pagada por no haber podido encolar
la siguiente sería el error caro.

**Decisión: el trabajo apunta a la captura y no a la extracción**, aunque el
assessment cuelgue de la extracción. Así `job_runs` no necesita una columna
nueva y el encargo significa «puntúa esta oferta», que es lo que se pide
desde la pantalla. El matiz es deliberado: si entra una reextracción entre
encolar y ejecutar, se puntúa la nueva, que es lo correcto.

**Lo único que M2 le ha tenido que cambiar a la mitad operativa de M1:
`latest_run_for_capture` y `latest_runs_for` ahora exigen el tipo de
trabajo.** Con un solo tipo, «el último trabajo de esta oferta» era una
pregunta sin ambigüedad; con dos, sin filtrar, un trabajo de scoring en
curso haría que la pantalla dijera que la **extracción** está en curso. El
parámetro es obligatorio y no tiene valor por defecto a propósito: es lo que
hace que el tercer tipo de trabajo no reintroduzca el fallo en silencio.

**Hallazgo relacionado: `status_of` mentía en una ventana concreta.** Tras
reextraer, el último trabajo de puntuación es el de la extracción anterior y
dice `succeeded`, pero la lectura de ahora no está puntuada. Ahora un
trabajo `succeeded` cuyo resultado no está vigente devuelve `none`. Tiene su
test.

**Decisión: la envoltura de estados de la tarea se extrajo a `_run_job`.** Lo
que centraliza no es código bonito: es marcar `running`, contar los
intentos y distinguir un fallo permanente de uno transitorio. Un tercer tipo
de trabajo escrito desde cero se olvidaría de alguna de las tres, y el
síntoma sería una fila en `running` para siempre.

**Hallazgo: `queue.py` y `tasks.py` se necesitaban mutuamente.** `queue.py`
importaba la función de la tarea para encolarla por su nombre, y ahora la
tarea necesita encolar. El ciclo se rompe con un mapa «tipo de trabajo →
nombre de tarea» en `jobs/vocabularies.py`, que no importa nada, y un test
ata esas cadenas a los nombres reales de las funciones y a lo que el worker
registra: arq encola por `__name__`, así que renombrar una función sin tocar
el mapa dejaría un trabajo que nadie sabe ejecutar.

### Repuntuar el histórico

**Decisión: `assessment/recompute.py`, ejecutable dentro del contenedor, sin
endpoint ni pantalla.** Es el camino real que el encargo pedía, y su test
comprueba la propiedad entera: dos ofertas puntuadas, se cambian los pesos,
se repuntúa recorriendo la base de datos, y las notas cambian **sin que
aparezca ni una llamada al modelo nueva**. Si algún día alguien «optimiza»
el recálculo llamando al LLM, ese test se cae.

**Decisión: no es un trabajo de la cola.** Un tercer tipo de `job_runs`
exigiría justificar qué significa reintentarlo y qué pasa si se queda a
medias, cuando lo que hace es idempotente: una fila ya repuntuada con el
modelo de hoy se salta, y eso se decide por el `sha256` del YAML y no por su
`version`.

**Decisión: una transacción por página y no una para todo.** Un barrido de
mil ofertas en una sola transacción bloquearía filas durante minutos, y si
fallara a mitad no habría avanzado nada.

**Decisión: repuntuar también revisa las referencias a evidencias.** Es lo
único que se recomprueba y no es aritmética: un `meets` apoyado en un bullet
que desde entonces ha dejado de estar `verified` o de ser divulgable ya no se
sostiene, y eso se puede saber sin preguntarle a nadie. Se degrada a
`partial` y queda registrado. Es la consecuencia útil de que el cruce viva en
esta capa: si viviera en la extracción, volver a cruzar exigiría reextraer.

**Decisión: una dimensión nueva en el modelo de scoring queda sin puntuar.**
No se le puede inventar nota. La consecuencia hay que aceptarla y está
probada: la cobertura baja, y si cae por debajo del mínimo la oferta se queda
sin puntuación hasta que alguien la vuelva a puntuar de verdad. Es lo
honesto: nadie ha mirado esa dimensión.

**Decisión: las correcciones de la fila anterior no se arrastran.** Eran la
cuenta de cuántas veces el modelo se saltó las reglas al responder, y la fila
recalculada no le ha preguntado nada. Arrastrarlas contaría dos veces la
misma infracción en cada repuntuación, y esa cuenta es la que decide si hay
que cambiar el prompt.

### La pantalla

**Decisión: el frontend no hace aritmética.** La API manda el ancho
(`weight_share`) y el alto (`score_share`) ya calculados. Si la pantalla
dividiera pesos para sacar anchos habría dos sitios donde se calcula lo
mismo, y el día que discreparan el dibujo diría una cosa y la puntuación
otra. Y como los pesos salen de la fila y no del YAML de hoy, la composición
de una oferta puntuada hace meses sigue sumando el 100% con **sus** pesos.

**Decisión: `value_score` y `coverage` viajan como cadena; los anchos y los
altos, como número.** La diferencia es a qué sirven: los primeros son la
puntuación, que se enseña tal cual y no se recalcula, así que va el texto
exacto de la base de datos —la misma regla que M1 aplicó a los importes—; los
segundos son geometría para CSS.

**Decisión: el hueco de lo no puntuable ocupa el alto completo de su
columna.** Lo que se enseña no es una nota baja: es que ahí falta
información y cuánto peso se lleva. Una barra a cero diría otra cosa, porque
cero **es** una nota.

**Hallazgo de la captura de pantalla, no del código: dos dimensiones sin
puntuar contiguas se leían como un solo bloque rayado.** Con un píxel de
separación sobre un fondo casi del mismo tono, el 20% y el 10% parecían un
30%. Ahora cada hueco lleva su marco discontinuo y la separación es de dos
píxeles sobre el fondo de la página.

**Decisión: el gráfico es una sola imagen con su descripción.** Leer «40%,
3, 30%, 3, 20%, sin puntuar» celda a celda no dice nada; la descripción
nombra cada dimensión con su peso y su nota. El detalle campo a campo está
debajo en texto, que es donde se puede leer de verdad, con la cita que
sostiene cada nota y el ancla del modelo de scoring que la explica.

**Decisión: los nombres de dimensión y de filtro se pintan humanizando el
identificador, sin traducir.** `expected_net_savings` sale como «Expected net
savings». Tener aquí un diccionario de traducciones sería duplicar en un
repositorio público el vocabulario del privado, que es justo lo que no se
hace. Es feo y no oculta nada, el mismo criterio que M1 aplicó a un campo
sin etiqueta. Los estados de filtro, los cubos y los niveles de esfuerzo sí
se traducen, porque son vocabulario de código.

**Decisión: `pending` se pinta en el color de alerta y no en el de fallo, y
con su propio símbolo (`○` frente a `▲`).** Es la confusión que el modelo de
scoring prohíbe, y un test del E2E comprueba que en una oferta con filtros
pendientes no aparece «no cumple» en ninguna parte.

**Decisión: el refresco automático cubre los dos trabajos.** Si solo mirara
la extracción, la página se quedaría quieta justo cuando aún falta la mitad,
porque la puntuación se encadena después.

**Decisión: el estado del repositorio de datos entra en `/api/health` y en la
página de estado.** Se comprueba **cargándolo** y no mirando si el
directorio existe: lo que hace funcionar el scoring no es que haya una
carpeta, son los seis YAML con la forma esperada. Es la diferencia entre «no
puntúa» y «no puntúa *por esto*». No cuenta para el estado general, y eso es
deliberado: hasta que M3 traiga el clon no existe en la VM, y marcar el
contenedor como enfermo por eso lo reiniciaría en bucle.

### El coste, observado en una llamada real

Cifras de la **primera llamada real** al modelo (2026-09-05, `gpt-5.6-terra`,
un anuncio inventado de tamaño medio), leídas de `llm_calls` y no estimadas:

| Llamada | Entrada | Salida | Razonamiento | Coste | Latencia |
|---|---|---|---|---|---|
| `offer_extraction` | 3.698 | 1.809 | 626 | $0,0291 | 18,3 s |
| `offer_scoring` | 5.113 | 1.982 | 980 | $0,0340 | 23,0 s |
| `cv_variant_choice` | 2.939 | 133 | 0 | $0,0075 | 2,3 s |

**M2 multiplica por 2,4 el coste por oferta: de ~$0,029 a ~$0,071.** El
presupuesto de `ARCHITECTURE.md` §13 (~1 €/mes) daba para unas 37 ofertas al
mes y ahora da para unas 15. Un anuncio más largo sube las tres cifras; el
bloque estable del prompt de scoring (~3.700 tokens) es el que la caché del
proveedor puede cubrir, y en esta primera llamada no la cubrió porque era la
primera.

La estimación previa a la llamada real —hecha con una aproximación de cuatro
caracteres por token— daba ~$0,089, un 25% de más. Se sustituye por lo
observado.

### Desviaciones deliberadas

- **`match`, `evidence_ref` y `cv_action` de `offer_requirements` se quedan
  en NULL para siempre**, en contra de dónde el contrato dibuja el cruce.
  Ver arriba el porqué; queda pendiente reflejarlo en
  `OFFER_DATA_CONTRACT.md` del repositorio privado.
- **`cv_action` no se rellena en ninguna tabla.** `ARCHITECTURE.md` §7
  descarta la adaptación fina por vacante, así que nadie lo consumiría.
- **El clon de solo lectura del repositorio privado sigue siendo M3.** Lo que
  M2 monta es la frontera; en producción `DATA_REPO_PATH` no está puesto y
  `/api/health` dice `not_configured`, que es la verdad.
- **La descarga del PDF de la variante es M3.** La pantalla lo dice en vez de
  dejar un botón que no hace nada.
- **El listado no cambia.** Meter ahí el `value_score` sería empezar la
  pantalla Pipeline, que no es esta rebanada, igual que el mapa valor ×
  probabilidad y el kanban.
- **Sin pantalla ni endpoint para repuntuar el histórico.** Es un módulo
  ejecutable en el contenedor, con su test. Una interfaz para eso no la pide
  nadie todavía.
- **Sin tests de componentes en el frontend.** Se añaden los de los
  ayudantes puros de `labels.ts`, y el comportamiento de la composición lo
  cubre el E2E contra el stack levantado. Montar un harness de componentes
  sería infraestructura nueva para una pantalla que no tiene interacción
  propia.
- **Siguen fuera shadcn/ui, TanStack, Motion, Sonner, cmdk, Recharts, Zod y
  `openapi-typescript`.** La composición ponderada son rectángulos con un
  ancho y un alto en porcentaje: se renderiza en servidor y funciona sin
  JavaScript, que es más de lo que daría una librería de gráficos.
- **Tres huecos de `config/scoring_model.yaml` se dejan como huecos**, con la
  interpretación anotada y visible en pantalla en vez de rellenada. Ver la
  sección siguiente.

### Tres huecos del modelo de scoring, y qué hace el código mientras

Los tres los ha destapado escribir la aritmética. Desde aquí no se escribe
en el repositorio privado, así que el código no los rellena: los enseña.

1. **`portfolio_assignment` no cubre `very_low`.** Reparte `high`, `medium` y
   `low`, y `effort_tier` sí contempla `very_low` (`cheap`), así que se
   espera que existan. El código deja `portfolio_bucket` en NULL **con su
   motivo**, que se pinta en pantalla. Asignarle `aspirational` sería
   inventarse una regla que nadie ha decidido; un hueco con su motivo hace
   que se arregle el YAML.
2. **`portfolio_assignment` no declara orden de evaluación y sus reglas se
   solapan.** Una oferta de familia fuera del objetivo con valor 2,0 encaja
   en `discard` y en `experimental` a la vez. El código aplica `discard` →
   `experimental` → reparto por banda, apoyándose en que el YAML dice de
   `discard` que no depende de la probabilidad. Es una interpretación y está
   anotada como tal en el código.
3. **El orden declarado de `effort_tier` tiene una consecuencia que parece un
   error.** Con `[skip, cheap, full, standard]`, una oferta de valor 4,4 sin
   ningún filtro en `fail` pero con alguno en `pending` sale `cheap` y no
   `full`, porque `cheap` se evalúa antes. La nota del YAML solo menciona el
   solape con `standard`. El código respeta el orden declarado sin
   corregirlo —el YAML manda— y hay un test cuyo único propósito es que
   dentro de un mes esto no parezca un fallo.

Un cuarto, menor: una familia de puesto **ausente** en la extracción no es
«fuera del objetivo». El código no dispara `experimental` con un NULL y
sigue al reparto por banda.

### Verificación en esta máquina, 2026-09-04

- `make check`: 22 tests de `cv_builder`, **294** de la API y **14** del
  frontend; ruff, `ruff format`, `mypy --strict`, eslint y `tsc --noEmit`
  limpios en los tres.
- `make migrate-check`: `upgrade`, `check`, `downgrade base` y `upgrade`
  otra vez, sin deriva, con la migración 0002 y su ciclo del vocabulario de
  `job_runs.kind`.
- `make up`: los seis servicios sanos, y `/api/health` con
  `data_repo: ok` contra el repositorio sintético montado de solo lectura.
- `make e2e`: los **10** tests de Playwright en verde, incluido el recorrido
  entero —pegar, extraer, **puntuar**, ver la composición— sin pedir la
  puntuación en ningún momento: la encadena la extracción.
- Una oferta inventada pegada por la API y puntuada por el worker de punta a
  punta, con sus cuatro dimensiones, tres filtros, cinco cruces de requisito
  y su variante en la base de datos.
- El cargador probado contra los **dos** repositorios: el sintético (cuatro
  dimensiones, cuatro variantes) y el privado real (seis dimensiones, cuatro
  filtros, cinco variantes, trece evidencias utilizables), sin tocar nada de
  este último.
- `python -m futuro_api.assessment.recompute` dentro del contenedor:
  idempotente en la primera pasada y repuntuando las cinco ofertas con
  `--force`.
- La composición ponderada revisada en una captura real, que es donde se vio
  el problema de los dos huecos contiguos.

**Sin verificar al cerrar M2:** una puntuación con el modelo de verdad. Todo
corría con `LLM_PROVIDER=stub`. Se hizo al día siguiente y tiene su propia
entrada abajo. El deploy sigue sin estrenar, así que el camino
`DATA_REPO_PATH` sin configurar en producción está probado en tests pero no
visto en la VM.

## 2026-09-05 — La primera llamada real, y lo que enseñó

M2 se cerró el 2026-09-04 con todo verificado contra `LLM_PROVIDER=stub`. Al
día siguiente se hizo la primera llamada real con `gpt-5.6-terra` y el
repositorio privado montado. Se anota aparte porque cambió tres cosas.

**Funcionó, y con cero correcciones en las dos llamadas.** Ni una cita
inventada, ni una nota sin cita, ni un filtro decidido sin poder citarlo, ni
una variante que no existe. Es el resultado que la cuenta de `corrections`
existe para medir, y en la primera oferta salió a cero. La variante elegida
vino además con el motivo en la forma que el prompt pide: por qué esa y
contra cuál la descartó.

**Hallazgo que hay que llevarse a `Futuro`, y es el cuarto hueco:
`expected_net_savings` quedó sin puntuar aunque el anuncio publicaba la
banda salarial.** El motivo que dio el modelo es exactamente el correcto:
«se publica salario bruto, pero no constan fiscalidad ni costes de vida
aplicables para calcular el ahorro anual frente a Madrid sin estimarlos». Las
anclas de esa dimensión están escritas **en euros de ahorro**, y llegar del
bruto al ahorro exige estimar impuestos y coste de vida, que es justo lo que
`missing_data.never` prohíbe.

La consecuencia es más fuerte de lo que se anotó al cerrar M2: no es que la
dimensión quede sin puntuar en los anuncios sin salario, es que **puede
quedar sin puntuar casi siempre**, incluso con salario publicado. Pesa 20
sobre 100. Mandar `baseline_madrid` en el prompt no lo arregla, porque el
problema no es la referencia sino el salto del bruto al ahorro. Las salidas
son de `Futuro`, no de aquí: reescribir esas anclas en términos de bruto, o
darle al modelo una fuente de fiscalidad y coste de vida que pueda citar.

**Defecto de la pantalla que solo los datos reales podían enseñar: un cero se
pintaba como una columna vacía.** El cliente simulado puntúa siempre un 3, así
que la altura nunca era cero; con el modelo de verdad,
`compensation_upside` sacó un 0 —anclado y bien razonado— y la barra
desaparecía, indistinguible de un hueco. Y esa distinción es medio proyecto:
un cero **es** una nota. Ahora la barra tiene un mínimo de dos píxeles y el
número se saca fuera cuando no cabe dentro.

**Fragilidad del E2E que apareció al apuntar al repositorio real:** dos
aserciones estaban atadas al vocabulario del repositorio sintético —el
nombre de una dimensión y el peso 40—, así que `make e2e` se caía en cuanto
`DATA_REPO_HOST_PATH` apuntaba al privado, aunque la aplicación funcionara.
Se sustituyen por comprobaciones de **forma**: que la etiqueta llega
humanizada —inicial en mayúscula, sin guiones bajos— y que el peso es un
número. Ahora el E2E pasa contra los dos repositorios, que es lo que tiene
que hacer un test cuyo objeto es el mecanismo y no el contenido de una
configuración.

**Decisión confirmada por Pablo el 2026-09-05: `baseline_madrid` va en el
prompt.** Se anotó al cerrar M2 como reversible y como decisión pendiente;
queda cerrada. Aunque, según el hallazgo de arriba, hoy no es lo que
desbloquea esa dimensión.

## 2026-09-05 — La versión 2 del modelo de scoring, implementada

`Futuro` cerró las cuatro decisiones que la llamada real destapó y publicó
`config/scoring_model.yaml` v2. Tres de ellas necesitaban código de este
lado, porque sus predicados viven en `assessment/scoring.py` y no en el YAML.

**`expected_net_savings` → `gross_compensation_vs_baseline`, midiendo contra
el bruto anual.** No necesitó ni una línea de código, y esa es la
comprobación de que el diseño era correcto: los nombres de dimensión son
vocabulario libre, y el cargador los lee del YAML en el trabajo siguiente.
Repuntuada la misma oferta con v2, la dimensión sacó un **4** —interpolando
entre el ancla de 3 (45.000-55.000) y la de 5 (≥70.000) para una banda
publicada de 55.000-70.000— donde con v1 quedaba sin puntuar. Era el
objetivo del cambio y se cumple.

**`very_low` pasa a `aspirational`.** El reparto por banda deja de ser un
`.get` con rama de reserva y pasa a ser una tabla, `BUCKET_OF_BAND`, indexada
directamente. Un test comprueba que cubre las cuatro bandas: sin él, añadir
una banda al vocabulario dejaría otra vez un hueco silencioso o un
`KeyError`. Se anota que el hueco **se arregló porque se veía**: el código no
se inventó el cubo, dejó el NULL con su motivo en pantalla, y eso es lo que
provocó la decisión.

**El orden de los cubos queda confirmado, no corregido.** `discard` →
`experimental` → reparto por banda era una interpretación de este código
porque el YAML no declaraba orden; ahora `portfolio_assignment.note` la fija
con sus motivos. El código no cambia; el docstring deja de decir «es una
interpretación».

**`cheap` se estrecha, y `full` deja de ser inalcanzable.** El hueco de
«filtros en pending» queda acotado a valor entre 3,0 y 4,0; `very_low` sigue
sin tope, porque tiene que ser `cheap` aunque el valor sea alto. Esa
asimetría es exactamente la razón por la que reordenar no servía. La misma
oferta de 4,40 con un filtro pendiente pasa de `cheap` a `full`.

### Un hallazgo que no es del scoring y conviene no perder

Repuntuar la **misma** oferta con v2 movió dos dimensiones cuyas anclas no
habían cambiado: `career_capital_and_brand` pasó de 1 a 3 —dos puntos en una
dimensión que pesa 20— y `compensation_upside` de 0 a sin puntuar. El valor
subió de 1,63 a 2,94, y solo una parte de esa subida es atribuible al cambio
de anclas.

Es variación del modelo, no un fallo del código: `llm/openai_client.py` no
fija `temperature` ni `seed`, así que dos llamadas con el mismo prompt no
tienen por qué coincidir. Las tres consecuencias, por orden de importancia:

1. **Repuntuar llamando al modelo no es idempotente**, y eso hace más valioso
   el recálculo sin modelo de `recompute.py`, que sí lo es: reutiliza los
   juicios guardados y solo rehace la aritmética.
2. Comparar dos ofertas puntuadas en llamadas distintas arrastra ese ruido,
   además del que ya arrastran por el `scoring_model_version`.
3. La capa append-only es lo que hace el problema **visible**: las dos
   puntuaciones están guardadas con su versión y su valor, y se ven una al
   lado de la otra en la pantalla.

**Se probó fijar `temperature = 0.0`, y `gpt-5.6-terra` lo rechaza.** La
llamada devuelve un 400 del proveedor: «Unsupported parameter: 'temperature'
is not supported with this model.» Es un modelo de razonamiento, y en esta
familia el muestreo no se controla por ahí. El cambio se revirtió el mismo
día sin llegar a commitearse; las tres llamadas de prueba fallaron antes de
facturar, así que costó cero.

Queda escrito para que no se vuelva a intentar. Las otras dos vías, sin
probar:

- `seed`, que tampoco se sabe si esta familia acepta y cuesta otra llamada
  averiguarlo. Y aunque lo aceptara, la documentación del proveedor lo
  describe como «best effort», no como una garantía.
- Aceptar la variación y apoyarse en que **`recompute.py` sí es
  idempotente**: reutiliza los juicios guardados y solo rehace la
  aritmética. Es lo que ya está construido, y es la razón por la que
  repuntuar el histórico no llama al modelo.

La conclusión práctica no cambia: repuntuar **llamando al modelo** no es
reproducible, repuntuar **sin llamarlo** sí, y la capa append-only es lo que
hace visible la diferencia.

## 2026-09-05 — El despliegue de M0, y lo que costó

M0 quedó cerrado al desplegar por primera vez a la VM de Oracle. El código
llevaba dos días verificado en local; lo que faltaba era la infraestructura,
que es trabajo manual sobre consolas externas. El procedimiento y las
trampas están en `docs/deployment.md`, sin valores concretos; los valores
viven en `Futuro`. Aquí van solo las decisiones.

**Decisión: `main` protegida con historial lineal y cero aprobaciones
requeridas.** `AGENTS.md` decía que `main` estaba protegida y no lo estaba.
Se configuró antes del primer merge, con los siete checks de `ci.yml` como
obligatorios. Cero aprobaciones porque GitHub no deja aprobar el propio PR y
exigir una bloquearía todos los merges para siempre. `enforce_admins`
desactivado a propósito: con él activado, un check colgado por una caída de
GitHub impediría desplegar un arreglo urgente.

**Consecuencia no prevista: historial lineal obliga a rebase, y el rebase
reescribe los SHA.** Eso rompió las excepciones de gitleaks, que estaban
escritas como huellas `commit:fichero:regla:línea`. El deploy se bloqueó
justo después del primer merge. **Huellas y merge por rebase son
incompatibles**, y la incompatibilidad la introdujo activar el historial
lineal media hora antes.

**Decisión: excusar gitleaks por contenido exacto del secreto.** No depende
de ningún SHA, así que sobrevive a cualquier rebase. Se usa la forma
singular `[allowlist]` y no `[[allowlists]]` con `condition`/`regexTarget`
porque esa sintaxis necesita una versión más nueva que la que trae
`gitleaks-action@v2`.

### Las cuatro trampas de gitleaks, por si vuelven

Costaron cuatro intentos. Las tres primeras son de mecánica de la acción y
están anotadas en el propio `ci.yml`:

1. **La acción no autodetecta `.gitleaks.toml`.** Pasa su propia `--config`
   y anula la detección que sí hace el binario. Se corrige con
   `GITLEAKS_CONFIG`.
2. **La acción ignora en silencio la sintaxis que no entiende.** Trae una
   versión más antigua que la de una máquina de desarrollo al día, y no
   avisa: el log dice que carga la configuración y la aplica a medias. La
   lección operativa es **probar con la misma versión que usa la acción**,
   no con la local. Un contenedor con la versión exacta resuelve la duda en
   un minuto.
3. **En un push escanea solo los commits nuevos; en un PR, el rango
   entero.** Un verde en push no demuestra que una excepción funcione.
4. **El fichero de excepciones también se escanea.** Documentar una
   excepción transcribiendo el valor que excusa crea un hallazgo nuevo en
   esa misma línea. Queda el aviso escrito donde toca.

Lo que **no** se hizo, y merece decirse: desactivar la regla, o excluir el
fichero entero. El job de `fugas de datos` es lo único que comprueba el
primer principio del repositorio, así que cada excepción se verificó
además con un commit de prueba que metía una credencial real en el mismo
fichero, comprobando que seguía saltando.

**Decisión: realinear `dev` con `main` tras el merge por rebase, con
force-push.** Las dos ramas tenían contenido idéntico y SHA distintos.
Dejarlo para después habría hecho que el siguiente PR arrastrase la misma
divergencia. Se usó `--force-with-lease` y se comprobó antes que el diff
entre ambas era vacío.

## 2026-09-05 — Las pantallas exigían sesión y no la exigían

Al probar el despliegue apareció que sin sesión se podía llegar a
`/capturar` y pegar una oferta. **No era un agujero de seguridad**: la API
responde `401` en todas sus rutas, comprobado contra producción, así que
nada de lo pegado se guardaba ni llegaba al modelo. Era una pantalla que se
dejaba usar para acabar en un error en inglés al enviar.

Sólo la pantalla de inicio, de M0, comprobaba la sesión. Las tres que
añadieron M1 y M2 no comprobaban nada.

**Por qué llegó a producción: `DEV_AUTH_BYPASS`.** En local autentica
siempre, así que el caso «sin sesión» no existe al desarrollar. Producción
fue el primer sitio donde se dio. Es el precio del bypass, que sigue
mereciendo la pena —desarrollar sin depender de Google— pero deja este punto
ciego: **lo que solo se rompe sin sesión no se ve en local**.

**Decisión: `requireUser` pregunta a la API, no mira la cookie.** Dos
motivos, y el segundo es el que descarta la alternativa: la cookie va
firmada y desde el frontend no se puede validar, y con el bypass hay sesión
**sin** cookie, de modo que un guardián basado en su presencia mandaría a la
pantalla de inicio en local y rompería el E2E entero.

**Decisión: guardián por pantalla, no middleware.** Un middleware de Next
protegería por omisión también las pantallas futuras, que es el patrón que
sigue la API. Se descartó porque en el Edge runtime solo puede mirar la
cookie, y eso choca de frente con el bypass. Como la API es el gate real,
olvidar el guardián en una pantalla nueva degrada a «error feo», no a fuga.

**Decisión: `make e2e` aborta si `LLM_PROVIDER` no es `stub`.** La suite
crea ofertas y cada oferta son dos llamadas al modelo. El `.env` local puede
quedarse apuntando al proveedor real tras una prueba manual —es exactamente
lo que había pasado, heredado de la primera llamada real de M2— y entonces
la suite cuesta unos 0,30 $ por ejecución. El fallo es silencioso: los tests
pasan igual, solo que despacio y facturando. Se descubrió después de gastar
0,74 $ en tres ejecuciones, visibles en la tabla `llm_calls` porque el
registro de coste que montó M1 sirvió justo para medirlo.

## 2026-09-05 — M3, entrega del PDF y dossier mínimo (cierra la Fase 1)

Con esto se cierra el troceo acordado el 2026-09-03. El alcance, según
`ARCHITECTURE.md` §14: descargar el PDF que CI ya construyó, confirmar o
cambiar la variante, y un dossier mínimo sin estados ni recordatorios —eso
es Fase 3—. Cero llamadas al modelo nuevas: el LLM ya eligió y citó en M2,
aquí solo hay disco y Postgres.

### El clon de solo lectura

**Decisión: la deploy key vive y muere en el runner de GitHub Actions, nunca
en la VM.** El job `deploy` clona `career-strategy` (superficial, `--depth
1`) con una clave nueva y de solo lectura —`DATA_REPO_DEPLOY_KEY`, distinta
de `DEPLOY_SSH_KEY`— y copia el árbol a la VM por `rsync` sobre la misma
conexión SSH que ya usa para `docker-compose.yml` y `Caddyfile`. La
alternativa —la clave persistida en la VM con un cron propio haciendo `git
pull`— se descartó a propósito: con la clave solo en el runner, una VM
comprometida no puede seguir clonando el repositorio privado por su cuenta.
Confirmado con Pablo el 2026-09-05.

**Decisión: el refresco va enganchado al deploy, no por su cuenta.** El
clonado ocurre en el mismo job que publica imágenes: cada push a `main`, o
cada `workflow_dispatch` manual, que ya existía. Un cambio en el repositorio
de datos no llega a producción hasta el siguiente merge o hasta que se
dispare a mano. Es deliberado y simétrico con `assessment/recompute.py`, que
tampoco corre solo: repuntuar tras un cambio en los datos ya era un gesto
manual, y refrescar el clon es un gesto de la misma familia. Confirmado con
Pablo el 2026-09-05, frente a la alternativa de un workflow con su propio
cron, más fresco pero desacoplado y con una pieza más que mantener.

**Decisión: `/opt/futuro/data/repo` es un directorio plano, no un volumen de
Docker gestionado.** Mismo patrón que `docker-compose.yml` y
`caddy/Caddyfile`: el runner lo escribe con `rsync`, Compose lo monta de
solo lectura. Meter un volumen gestionado habría exigido un contenedor
aparte solo para volcar el clon dentro, sin ganar nada.

**Decisión: `DATA_REPO_PATH` pasa a la lista de obligatorias con
`ENV=production`.** Era la reversión que M2 ya anticipó al montar la
frontera antes que el clon. Hasta hoy no arrancar sin él habría tumbado la
aplicación entera por una función que no podía funcionar; con el clon ya en
la VM, seguir arrancando sin él sería el mismo agujero que `AGENTS.md`
prohíbe para el resto de secretos de producción.

**Desviación del nombre de la documentación:** `Futuro` es como se nombra el
repositorio privado en toda la documentación, pero el repositorio de GitHub
se llama en realidad `career-strategy`. `deploy.yml` y `docs/deployment.md`
usan el nombre real donde hace falta un `git clone`, y anotan la
equivalencia para que no parezca un error de transcripción.

### Localizar el PDF

**Decisión: `data_repo.pdf_path()` localiza por extensión, no por
plantilla de nombre.** El nombre real de un PDF es
`Pablo_Coma_CV_<variante>_<idioma>.pdf`, con `<idioma>` decidido por
`Futuro` —hoy `en` para las cinco—; el repositorio sintético de los tests
usa `CV_<variante>_es.pdf`, con otro prefijo y otro idioma, a propósito.
Si el localizador dependiera del nombre exacto, ese repositorio sintético
no lo habría destapado nunca. Un glob por `*.pdf` dentro de la carpeta de la
variante —ya validada como `available` por el cargador de M2— encuentra el
documento sin dar por supuesto de qué repositorio viene.

**Decisión: cero o más de un PDF es un fallo cerrado y ruidoso, igual que el
resto de `data_repo`.** El workflow `build-cvs` borra el contenido de la
carpeta antes de copiar el PDF nuevo, así que exactamente uno es la única
forma honesta; cualquier otra cosa es un repositorio con una forma que no
se esperaba, y se dice en vez de elegir un PDF al azar.

**Verificado contra los dos repositorios, sin tocar nada del privado:** el
cargador sintético con sus cuatro PDF de mentira añadidos a los fixtures
—antes de M3 no había ninguno—, y una lectura de solo lectura de
`/Users/valbu/Desktop/Futuro` que confirmó las cinco rutas reales
(`Pablo_Coma_CV_<variante>_en.pdf`) sin escribir nada.

### El dossier mínimo: la tabla `applications`

**Decisión: se adopta ya el nombre `applications` que reserva
`docs/OFFER_DATA_CONTRACT.md`**, aunque hoy solo tenga tres columnas de las
suyas. La alternativa —una tabla `offer_dossiers` propia de M3 y una
`applications` de verdad en Fase 3— se descartó porque habría exigido
decidir después si migrar filas o convivir con dos tablas. Con el nombre
final desde ahora, Fase 3 añade `status`, `channel`, `submitted_at`,
`follow_up_at`, `outcome` e interacciones con un `ALTER TABLE` aditivo: la
misma disciplina de migraciones compatibles hacia atrás que ya sigue el
resto del esquema. Confirmado con Pablo el 2026-09-05, frente a la
alternativa de una tabla `offer_dossiers` estrecha.

**Decisión: cuelga de `offer_captures`, no de la extracción ni del
assessment.** Confirmar una variante es un gesto de Pablo sobre *la
oferta*, el mismo principio que ya aplica `job_runs.capture_id`: si entra
una reextracción entre medias, lo que cambia es qué recomendación se puede
confirmar, no la identidad de qué oferta se está preparando.

**Decisión: append-only, con el mismo trigger de inmutabilidad que las
otras capas.** Cambiar de variante crea una fila nueva y no edita la
anterior, así que queda el historial de qué confirmó Pablo primero y qué
decidió después —el mismo motivo que M1 y M2 ya dieron para sus capas—.
Vigente es la última por `(confirmed_at, id)`.

**Decisión: `recommendation_id` es nullable y `SET NULL` al borrar.** Deja
constancia de si la confirmación coincide con lo que dijo el modelo o lo
descarta, pero no lo exige: nada impide confirmar una variante sin que
exista ninguna recomendación vigente —el trabajo de puntuación pudo fallar,
o no haberse pedido nunca, y los cinco PDF ya existen igual—.

**Decisión: `cv_sha256` se calcula sobre el PDF servido en el momento de
confirmar, no se copia de ninguna otra fila.** Es el mismo dato que
`docs/OFFER_DATA_CONTRACT.md` pide para `applications.cv_sha256` —"lo que
permite afirmar meses después qué documento exacto se mandó"—, y calcularlo
del fichero real en vez de fiarse de un campo asegura que dice la verdad
aunque el PDF de esa variante cambie más tarde por un rebuild de `Futuro`.

### Los dos endpoints

**Decisión: `GET /api/offers/{id}/cv` y `POST /api/offers/{id}/dossier` no
comparten código de servir bytes.** El primero sirve cualquier variante
disponible, con o sin confirmar —es lo que permite mirar un PDF antes de
decidir—; el segundo registra una confirmación y devuelve JSON, nunca
bytes. Separar «ver» de «decidir» es el mismo principio que ya aplicó M1 a
extracción y reextracción.

**Decisión: sin `?variant=`, `GET .../cv` sirve lo confirmado y, si no hay
nada confirmado todavía, lo recomendado.** Es lo que hace que el enlace de
descarga por omisión siga siendo el correcto después de que Pablo cambie de
variante, sin que la pantalla tenga que decidir cuál pedir.

**Decisión: sin repositorio de datos, sin recomendación y sin variante
explícita, cada caso tiene su código y no un 500 genérico.** 503 cuando el
repositorio de datos no está configurado o no se puede leer —mismo criterio
que `/api/health`, cargándolo y no mirando si el directorio existe—; 409
cuando no hay ninguna variante que servir por omisión; 422 cuando la
variante pedida no está entre las disponibles. Ningún camino deja una
respuesta ambigua sobre qué falló.

**Decisión: `OfferDetail.available_variants` se carga con manga ancha, sin
lanzar.** A diferencia de los dos endpoints de arriba, que sí tienen que
fallar cerrado porque van a *actuar*, el detalle de una oferta solo
necesita *pintar* la lista de variantes elegibles; un repositorio de datos
roto no debería tumbar el resto del detalle —la extracción, la puntuación—
por una lista que ni siquiera se está usando para decidir nada en esa
petición. Vacía significa "no se puede cambiar de variante ahora", y la
pantalla lo dice en vez de ocultar el resto.

**Desviación deliberada de "solo el worker depende del repositorio de
datos"**, que M2 dejó escrito. Servir un PDF y confirmar una variante son
peticiones síncronas de `api`, así que `api` también necesita el volumen
montado desde M3; el comentario que lo decía en `data_repo/loader.py` y en
`docker-compose.override.yml` queda corregido donde estaba escrito.

### La pantalla

**Decisión: sin JavaScript propio, igual que el botón de puntuar.** Cada
variante disponible es una fila con un enlace `<a>` directo a
`/api/offers/{id}/cv?variant=...` —Caddy lo enruta al mismo origen, así que
la cookie de sesión viaja sola— y, si no es ya la confirmada, un
`<form action={confirmVariant}>` con la misma acción de servidor y
`revalidatePath` que ya usa `requestAssessment`. La fila de la variante
confirmada no lleva botón: no hay nada que confirmar dos veces.

**Decisión: la sección se llama "Variante de CV" y no "... recomendada".**
Ahora enseña tres cosas —la recomendación del modelo, la confirmación de
Pablo si la hay, y las opciones para cambiarla— y el título viejo solo
nombraba la primera.

### Desviaciones deliberadas

- **Sin estados, canal, fecha de envío, recordatorio ni interacciones en
  `applications`.** Están reservados en el nombre de la tabla y en
  `docs/OFFER_DATA_CONTRACT.md`, pero son Fase 3.
- **Sin exportar el dossier a Markdown en `Futuro`.** El contrato lo
  menciona (`opportunities/`), pero también es posterior: hoy no se escribe
  nada en el repositorio privado desde esta aplicación, ni falta que hace
  para un dossier mínimo.
- **El botón «Puntuar» / «Volver a puntuar» sigue sin deshabilitarse cuando
  `data_repo` no está configurado**, que es el detalle que M2 dejó anotado
  para cubrir "de paso" en M3. Se decidió no tocarlo: mientras se escribía
  M3 el repositorio de datos estuvo siempre configurado —local con el
  sintético o con el real, y en producción desde el clon de este mismo
  hito—, así que no había forma de verlo ni de probarlo sin desconfigurar
  algo a propósito. Sigue siendo el `PermanentFailure` correcto si alguien
  lo pulsa; solo la pantalla del botón se queda como estaba.

### Verificación en esta máquina, 2026-09-05

- `make e2e` en verde antes de tocar código: harness heredado sano.
- `uv run ruff check .`, `ruff format --check .`, `mypy` y `pytest` (316
  tests, con Postgres real) limpios en `services/api`.
- `alembic upgrade head` → `check` → `downgrade base` → `upgrade head` con
  la migración `0003`, sin deriva.
- `npm run lint`, `npm run typecheck` y `npm run test` (17 tests) limpios en
  `services/web`.
- `make e2e`: 12 tests en verde, incluidos los dos nuevos de
  `dossier.spec.ts` —confirmar y descargar—, corridos contra el
  repositorio privado real montado en local (`DATA_REPO_HOST_PATH`
  apuntando a `/Users/valbu/Desktop/Futuro`), no solo el sintético.
- `data_repo.pdf_path()` probado a mano contra el repositorio privado real,
  de solo lectura, confirmando las cinco rutas
  `Pablo_Coma_CV_<variante>_en.pdf`.
- La pantalla revisada en una captura real tras confirmar una variante: el
  aviso de confirmación, la fila confirmada sin botón de confirmar, y las
  cuatro filas restantes con su enlace y su botón.

## El primer despliegue de M3, y lo que enseñó

La deploy key de solo lectura se provisionó con `gh` el mismo 2026-09-05:
par ed25519 nuevo, pública como *deploy key* de `career-strategy` —confirmada
`read-only` en el listado, no `read-write`— y privada como el secreto
`DATA_REPO_DEPLOY_KEY` del Environment `production`, sin dejar copia en el
Mac. El PR de `dev` a `main` fue directo salvo un tropiezo conocido:
`dev` tenía dos commits con el mismo contenido que `main` pero SHA
distintos —el rebase-merge anterior ya los había reescrito— y el nuevo
rebase-merge no podía crear el commit limpio. Es exactamente lo que
`docs/decisions/fase-1-nucleo.md` ya documentó al cerrar M0: se realineó
`dev` con `git rebase origin/main` —que descarta solo los commits ya
aplicados, comprobado con un `diff --stat` vacío antes de tocar nada— y un
`push --force-with-lease`.

**Hallazgo en el primer deploy real: `git clone` sin `--branch` trae la
rama por omisión del repositorio, y no es donde vive el contenido.**
`/api/health` respondió `data_repo: unreadable`, con el motivo exacto —tres
ficheros ausentes— porque `data_repo.load()` falla cerrado y dice qué
falta. `career-strategy` declara `main` como rama por omisión en GitHub,
pero es un árbol antiguo y sin relación (`app/`, `pipeline/`, sin `cv/` ni
`config/scoring_model.yaml`): el contenido de verdad vive en `dev`, el
mismo convenio que sigue este propio repositorio. Se corrigió fijando
`git clone --depth 1 --branch dev` en `deploy.yml`. Ninguna otra pieza
falló: el mensaje de error señaló la causa exacta sin tener que mirar
logs, que es precisamente lo que "falla cerrado y con el motivo" está para
conseguir.

## Fase 1 cerrada

Con M3, las cuatro rebanadas de la Fase 1 —esqueleto, ingesta y extracción,
scoring y recomendación de variante, y entrega del PDF con dossier
mínimo— están completas, desplegadas y verificadas contra producción:
`/api/health` en `data_repo: ok` tras el segundo deploy, con el clon de
verdad en `/opt/futuro/data/repo`. La siguiente fase, la 2 (perfil
editable), es la primera que escribe en el repositorio privado y necesita
la mecánica de `pull --rebase`, diff y confirmación de `ARCHITECTURE.md`
§5.
