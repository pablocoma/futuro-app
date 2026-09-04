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
