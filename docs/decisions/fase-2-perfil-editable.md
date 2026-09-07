# Fase 2 — Perfil editable

Ver `ARCHITECTURE.md` (repositorio privado `Futuro`) §5 para la mecánica de
escritura cerrada de antemano (`pull --rebase` → cargar con `ruamel.yaml` →
validar → diff → confirmar → commit → push) y §14 para el alcance de la
fase. Este documento recoge solo las decisiones de implementación tomadas
aquí, y se amplía con cada rebanada (M0 → M4).

El troceo en cinco rebanadas —M0 sobre `config/objectives.yaml`, M1 sobre
`preferences.yaml`/`constraints.yaml`, M2 sobre el banco de bullets y el
contenido de variantes, M3 sobre `cv_variants.yaml`/`project_catalog.yaml`,
M4 sobre `scoring_model.yaml`— se acordó con Pablo el 2026-09-06 y está en
`NEXT_SESSION.md`.

## 2026-09-06 — Shell mínimo, antes de M0

`docs/APP_SCREENS.md` (repositorio privado) documenta un shell de siete
pantallas —barra lateral en escritorio, inferior en móvil, `⌘K`
contextual— pero anota explícitamente que no está construido. M0 es la
primera vez que hace falta llegar a una pantalla nueva ("Perfil") desde
algún sitio, así que tocaba decidir qué construir del shell y cuándo.

**Decisión: shell real, pero con solo las tres entradas que hoy tienen
pantalla de verdad.** Pipeline (`/ofertas`), Capturar (`/capturar`) y
Perfil (`/perfil`, nueva). Nada de Hoy, Oferta suelta, CVs ni Stats: cuatro
de las siete pantallas documentadas no tienen ruta construida todavía, y
enlazar a la nada es peor que no tener el enlace. Se completan una a una
cuando su fase construya la pantalla real detrás —Fase 3 para Pipeline de
verdad y Hoy, Fase 5 para Stats—.

**Decisión: `/` —la página de estado de M0 de Fase 1— se queda fuera del
shell.** Sigue accesible por URL directa. Qué es "Hoy" de verdad —¿la
misma página de estado, o algo nuevo?— es una conversación de diseño
aparte, no algo que resolver de paso aquí.

**Decisión: sin `⌘K` todavía.** El documento lo describe como saltos
contextuales a vistas que hoy no existen (mapa de Pipeline, matriz de CVs,
embudo de Stats). Una paleta de comandos vacía no aporta nada.

**Decisión: un route group `(shell)/` en vez de tocar el layout raíz.**
`app/(shell)/layout.tsx` envuelve `capturar/`, `ofertas/` y `perfil/` con
`<Shell>`, que pinta la barra lateral y la inferior; `app/page.tsx` (la
portada) queda fuera del grupo y no lleva chrome. El nombre entre
paréntesis no aparece en la URL, así que `/capturar` y `/ofertas/[id]`
siguen siendo las mismas rutas de siempre —nada que actualizar en el e2e
existente por un cambio de URL—.

**Decisión: `requireUser()` sube al layout del grupo.** Las tres páginas
que antes lo llamaban cada una por su cuenta (`capturar`, `ofertas`,
`ofertas/[id]`) descartaban el valor de vuelta; hoy lo pide una vez el
layout y cubre también `/perfil` sin que su página tenga que acordarse.

**Decisión: el harness de estructura es Playwright comprobando qué existe
y en qué orden, no comparación de píxeles** —mismo patrón que
`dossier.spec.ts` en Fase 1—. `shell.spec.ts` comprueba las tres entradas
en orden en escritorio, las mismas en móvil, y que la barra que no
corresponde al viewport está en el DOM pero oculta.

### Verificación en esta máquina, 2026-09-06

`make check` limpio (316 tests API + 17 web), `make e2e` con los 16 tests
en verde incluidos los 3 nuevos de `shell.spec.ts`, y capturas de pantalla
de escritorio y móvil revisadas a mano.

## 2026-09-06 — M0, el mecanismo de escritura sobre `config/objectives.yaml`

Investigado antes de escribir código: `config/objectives.yaml` seguía
teniendo la forma asumida al trocear (32 líneas, 6 claves sin anidar) y no
se había tocado desde el commit inicial de `career-strategy`; y solo
existía una deploy key en ese repositorio, la de solo lectura de M3.

### El clon de lectura-escritura, y su deploy key

**Decisión: esta clave persiste en la VM, a diferencia de la de M3.** La
de M3 vive y muere en el runner de GitHub Actions porque solo la usa el
propio deploy, una vez por push. Esta la usa la propia app en cualquier
momento futuro —cuando alguien confirma un cambio desde el navegador—, así
que tiene que estar disponible fuera de una ejecución de CI. Es la
consecuencia directa de "gestionado por la propia aplicación"
(`ARCHITECTURE.md` §5), no un descuido: cambia el modelo de amenaza de
verdad, y `ARCHITECTURE.md` §15 ya tenía una fila para este riesgo
concreto ("Deploy key con escritura filtrada"). El detalle completo, y el
procedimiento de aprovisionar, está en `docs/deployment.md` §10.

**Decisión: la clave nunca pasa por un secreto de GitHub Actions.** Se
copia a mano a `/opt/futuro/data-repo-write.key`, el mismo patrón que
`/opt/futuro/.env` —"se escribe a mano una vez y no pasa nunca por CI"—,
en vez de forzarla al patrón de las otras dos claves, que sí encajan ahí
porque solo las usa un workflow.

**Decisión: el `known_hosts` de GitHub se commitea, la clave privada
nunca.** Las huellas SSH de `github.com` son públicas
(`https://api.github.com/meta`); `services/api/git/github_known_hosts` las
trae fijadas para que `StrictHostKeyChecking=yes` falle en vez de
preguntar de forma interactiva —imposible en un contenedor— si GitHub
cambiara de clave.

**Decisión: solo `api` monta el clon y la clave, no `worker`.** Las
escrituras del perfil son síncronas dentro de la petición HTTP de
`/api/profile/*` —no hay llamada al LLM que justifique una cola, a
diferencia de extracción y scoring—, así que el worker no tiene motivo
para tener la clave.

### El mecanismo genérico (`data_repo_write/git_ops.py`)

**Decisión: `-c safe.directory=*` en cada invocación, nunca `HOME` ni
configuración global.** El directorio de trabajo es un volumen montado
desde el host con su propio dueño, no el `uid` del contenedor; git
moderno se niega a operar ahí ("detected dubious ownership") sin esto. Se
fija por invocación y no en un `.gitconfig` porque cada llamada ya declara
con `-C` cuál es el único repositorio sobre el que opera: es tan seguro
como acotarlo a la ruta exacta.

**Decisión: la identidad de autor/committer también se pasa con `-c` en
cada invocación, incluida `pull --rebase`.** Rebasar reescribe el
committer de cada commit que reproduce, así que hace falta identidad ahí
también, no solo en el commit final, o git se niega con "please tell me
who you are" en cuanto haya algo que reproducir. Se descubrió con un test
que reproducía una carrera de verdad —dos clones escribiendo al mismo
remoto— y fallaba justo en el reintento.

**Decisión: `commit_and_push` recibe la lista de ficheros a añadir,
nunca `git add -A`.** Este clon es de la app y solo debe llevar lo que
esta escritura tocó, no lo que otra escritura a medias pudiera haber
dejado.

**Decisión: un conflicto aborta y no fuerza nada, en `pull --rebase` y en
`push`.** El único intento de recuperarse solo es un reintento de `push`
tras un `pull --rebase` fresco —el caso de una carrera con otra
escritura, no un choque de contenido—. Si el segundo intento también
choca, se propaga el conflicto tal cual.

**Hallazgo: confirmar sin haber cambiado nada hacía fallar `git commit`
con "nothing to commit", y eso subía como un 500.** No es un error: es que
el repositorio ya refleja lo que se pedía. `commit_and_push` lo detecta
con `git diff --cached --quiet` antes de intentar el commit, y devuelve el
`HEAD` actual sin tocar el remoto.

**Hallazgo importante para M1-M4: el reemplazo estructurado de campos hace
que una carrera en el mismo campo casi nunca choque a nivel de git.**
Como cada escritura reconstruye el valor final desde el formulario en vez
de aplicar un parche de texto, dos escrituras concurrentes al mismo campo
no producen un conflicto de *rebase* salvo en la ventana estrechísima
entre el commit y el push propios —el caso que sí prueba
`test_commit_and_push_no_fuerza_un_conflicto_de_verdad`—. Fuera de esa
ventana, "gana" quien confirma último, silenciosamente. No se ha
resuelto aquí —añadir control de concurrencia optimista (por ejemplo,
exigir el `sha256` del fichero que se vio al abrir el formulario) es una
decisión de UX, no una corrección de bug— pero conviene tenerlo presente
al construir M1-M4, sobre todo en ficheros que varias pantallas puedan
editar a la vez.

### `objectives.py` y el estilo del YAML

**Decisión: el estilo de indentación se iguala al fichero real, no al que
`ruamel` trae por omisión.** Comprobado con el `Futuro` real (local, de
solo lectura) el 2026-09-06: `YAML(typ="rt")` con
`indent(mapping=2, sequence=4, offset=2)` reproduce byte a byte el
fichero sin tocar nada, mientras que la configuración por omisión de
`ruamel` no indenta las listas bajo su clave. Sin esto, cada edición
ensuciaría el diff con un reformateo completo del fichero, no solo el
campo que cambió.

**Decisión: `expected_tenure_years` se muta en su sitio, no se
reemplaza.** El fichero real lo escribe en flujo (`[2, 4]`); asignar una
lista de Python nueva pierde esa marca y lo convierte en bloque.
Reemplazar los dos elementos del `CommentedSeq` existente conserva el
flujo.

**Decisión: `primary_objective.statement` se escribe de vuelta con
`FoldedScalarString`.** El fichero lo declara en bloque plegado (`>-`);
sin envolver el texto nuevo en ese tipo, `ruamel` lo escribiría como una
cadena entrecomillada de una sola línea.

**Decisión: `updated_at` se valida como `date`, no como `str`.** YAML sin
comillas lo carga como `datetime.date`; declararlo `str` en el modelo
rompía la validación con un mensaje confuso. Se estampa con la fecha de
hoy en cada escritura, y no es un campo del formulario.

**Decisión: `role_families` valida contra `RoleFamily` —vocabulario de
código, no del repositorio privado— y el lado de lectura no.** El
cargador de solo lectura (`data_repo/loader.py`) transporta los nombres de
`role_families.core` sin comprobarlos, a propósito, para que un dato de
prueba con un nombre inventado no rompa nada. El lado de **escritura** es
más estricto porque puede permitírselo: exige que cada nombre sea uno de
los ocho valores declarables del enum (todos salvo `other`, que es el
motivo de "no encaja en ningún objetivo" y no algo que se declare), y
rechaza duplicados entre `core` y `exploratory`. Es la puerta que evita
que un typo deje una familia inalcanzable en silencio.

**Decisión: `prepare`/`write` revalidan el documento completo tras
aplicar la edición, no solo los campos que el formulario tocó.** `version`
no está en `EditableObjectives`, pero si quedara corrupta por algo ajeno a
esta app —una edición a mano en el repositorio privado, un merge raro—,
la escritura tiene que notarlo igual. Probado corrompiendo `version` a
mano en el fixture y confirmando que `prepare` lo rechaza sin escribir
nada.

**Decisión: `diff` y `commit` son dos operaciones que recalculan todo
desde cero —`pull`, carga, aplica, valida— en vez de que `diff` deje algo
pendiente para que `commit` reutilice.** Nada expira, nada se queda a
medias si se cierra la pestaña entre ver el diff y confirmar. El coste de
releer un YAML pequeño dos veces es irrelevante al lado de la llamada al
LLM que sí espera esta misma app en otras pantallas.

### La pantalla, y dos hallazgos de React/Next que costaron tiempo

**Hallazgo: un fichero `"use server"` solo puede exportar funciones
async.** `actions.ts` exportaba también `INITIAL_OBJECTIVES_STATE` (un
objeto) para que `ObjectivesForm.tsx` lo reutilizara, y esa exportación
rompía el módulo entero en tiempo de ejecución ("A 'use server' file can
only export async functions, found object"). El valor inicial se movió al
propio componente cliente, que es quien lo necesita; el fichero de
acciones solo exporta `reviewObjectives` y el tipo `ObjectivesFormState`
—un tipo se borra en tiempo de compilación, así que no cuenta—.

**Hallazgo, más caro de encontrar: React resetea los campos no
controlados de un `<form action={...}>` en cuanto la acción del servidor
termina.** Es el comportamiento pensado para un formulario que se limpia
solo tras publicar algo, pero aquí es justo lo contrario de lo que hace
falta: lo que se ve en el diff tiene que seguir en el formulario cuando se
pulsa «Confirmar y guardar» justo después. Con `defaultValue`, el
`commit` escribía siempre el valor **original**, nunca lo editado —y como
en ese caso no había nada que cambiar, `git commit` fallaba con "nothing
to commit" y eso disparó el hallazgo de arriba—. Se corrigió convirtiendo
todos los campos a controlados (`value` + `onChange` con estado de React),
que no se ven afectados por el reseteo.

**Decisión: familias de rol como radios agrupados, no texto libre.** Un
`<fieldset>` por familia con tres opciones —ninguna / core /
exploratoria— hace imposible mandar una familia repetida o con un nombre
que el enum no reconoce, en vez de dejar que el 422 de la API lo diga
después de escribir a mano. `success_dimensions`, en cambio, sigue siendo
texto libre separado por comas: no hay vocabulario cerrado que proteger
ahí todavía.

**Decisión: un único `useActionState`, y qué botón se pulsó decide diff o
commit.** `<button name="intent" value="diff">` y
`<button name="intent" value="commit">` en el mismo `<form>`; el servidor
lee `formData.get("intent")`. Evita mantener dos acciones y dos estados
sincronizados a mano.

### Desarrollo local

**Decisión: un repo bare local hace de "GitHub" en desarrollo.** `make
seed-data-repo-write` (enganchado a `make up`) siembra
`.dev-data/repo-write-remote.git` desde
`services/api/tests/fixtures/data_repo_write/` una sola vez; la propia app
lo clona a `.dev-data/repo-write` la primera vez que lo necesita.
Apuntar al `Futuro` real es una línea en `.env`
(`DATA_REPO_WRITE_REMOTE=git@github.com:...`), igual que ya vale para
`DATA_REPO_HOST_PATH`, aunque requiere además montar una clave propia a
mano —no está enganchado por `.env` solo, ver `docker-compose.override.yml`—.

**Decisión: fixture propio para el remoto de escritura, distinto del de
lectura.** `tests/fixtures/data_repo/config/objectives.yaml` solo lleva lo
que el cargador de solo lectura toca (ni `success_dimensions` ni
`transition.urgency` existen ahí) y a propósito incluye nombres de familia
inventados para probar que el lado de lectura no los rechaza.
`tests/fixtures/data_repo_write/` lleva el fichero completo, con familias
todas reales: el modelo de escritura sí las rechazaría.

### Desviaciones deliberadas

- **`GET /api/profile/objectives` también hace `pull --rebase`.**
  `ARCHITECTURE.md` §5 solo lo exige "antes de escribir", pero enseñar el
  formulario con datos ya desactualizados es la manera más segura de
  acabar chocando en el commit.
- **Sin control de concurrencia optimista** (ver el hallazgo de la carrera
  sin conflicto, arriba). Queda para cuando haga falta de verdad.
- **`success_dimensions` sigue siendo texto libre.** No hay vocabulario de
  código que proteger ahí todavía, a diferencia de `role_families`.

### Verificación en esta máquina, 2026-09-06

`make check` limpio (336 tests API —157 nuevos de `data_repo_write`— + 17
web), `make e2e` con los 17 tests en verde incluido el recorrido nuevo de
`perfil.spec.ts`. Además, contra el stack de Compose real —no solo
`pytest`—: `docker compose up --build`, clon en frío desde el bare local,
`GET`/`diff`/`commit` por `curl`, commit real en el remoto con la autoría
`Futuro App <bot@futuro.local>`, y el recorrido completo repetido a mano
en el navegador con Playwright, incluida la reproducción y corrección de
los dos hallazgos de React de arriba.

**Sin verificar, y no se puede desde aquí:** la deploy key de verdad y el
directorio en la VM de producción. `docs/deployment.md` §10 describe el
procedimiento; queda pendiente de que Pablo lo ejecute antes del próximo
merge a `main` que quiera llevar Fase 2 a producción.

## 2026-09-07 — M1, generalizar el mecanismo a `preferences.yaml` y `constraints.yaml`

### La investigación corrigió el troceo, no lo confirmó

`NEXT_SESSION.md` daba por hecho, desde el troceo del 2026-09-06, que
`pending_decisions` y `superseded_decisions` eran "listas de
diccionarios". Investigado el `career-strategy` real antes de escribir
código: los dos ficheros no se habían tocado desde el 2026-08-13 y sus
tamaños son exactos (68 y 60 líneas), pero esa forma concreta era
incorrecta:

- `pending_decisions` es una **lista plana de strings** -el mismo patrón
  que `success_dimensions`/`role_families` de M0-, no una lista de
  diccionarios.
- `superseded_decisions` es un **mapa de clave -> texto**, no una lista.
- La complejidad real de "lista de diccionarios heterogénea" está en
  **`disqualifying_conditions`**, que el troceo no mencionaba: cada
  elemento trae `id` + `rule`, y además `evaluable_from_posting` *o*
  `affects` según el caso.

Por grep en `services/api/src` antes de diseñar: **ningún campo de los dos
ficheros es vocabulario de código**, salvo `disqualifying_conditions.id`/
`.rule`, que `assessment/prompt.py` mete como texto libre en el prompt del
modelo -no se compara contra ningún enum en ningún sitio, a diferencia de
`role_families`-. No hace falta ninguna puerta de vocabulario nueva en
`models.py` para M1.

### Hallazgo de fondo: reasignar un valor sin cambiarlo puede ensuciar el diff

Antes de escribir `preferences.py`/`constraints.py` se repitió el
experimento de ruamel que ya había servido en M0, esta vez contra
`constraints.yaml` real, con un resultado que obligó a rediseñar el
mecanismo:

- Envolver un texto en `FoldedScalarString` de nuevo -incluso con el mismo
  texto aplanado que ya había- lo reenvuelve con el ancho por omisión de
  `ruamel`, que no coincide con el ancho a mano del fichero real. El
  resultado es un diff que cambia una línea de un campo que el usuario no
  tocó.
- Reemplazar una `CommentedSeq` entera, o incluso mutarla con un
  slice-assign de contenido idéntico, puede perder la línea en blanco de
  cierre que quedó asociada a su último elemento.

Comprobado contra `objectives.yaml` real: **`_apply()` de M0 ya tenía este
bug**, sin que nadie lo hubiera visto. `primary_objective.statement` se
reasigna en cada escritura sin comprobar si cambió; editar solo
`target_year` y dejar la declaración intacta reflowaba igualmente su
línea. Nunca se detectó en M0 porque solo hay un campo plegado y las
verificaciones siempre tocaban también la declaración a la vez. Con M1
esto habría sido crítico: los dos ficheros nuevos traen nueve campos de
texto plegado entre los dos, y sin corregirlo casi cualquier edición
habría reformateado media prosa del fichero sin motivo.

**Corrección: comparar antes de reasignar, y no tocar nada si no cambió de
verdad.** `data_repo_write/yaml_style.py` reúne la configuración de
`ruamel.yaml` -antes duplicada en `objectives.py`, decisión 4A confirmada
con Pablo, ahora sí compartida entre los tres módulos porque divergir en
uno solo reformatearía ese fichero entero en su próximo commit sin que
nadie lo note- y dos funciones nuevas:

- `set_folded_if_changed(mapping, key, text)`: no construye siquiera el
  `FoldedScalarString` si el texto no cambió.
- `set_string_list_if_changed(container, key, values)`: muta la
  `CommentedSeq` en su sitio (`[:]`, nunca reemplaza la clave entera) y
  solo si la lista difiere de la que ya hay.

`objectives.py` se retocó para usar las dos -mismo comportamiento hacia
fuera, corrige el bug de `primary_objective.statement`-, con un test de
regresión nuevo (`test_prepare_no_reflowa_un_campo_plegado_que_no_cambio`)
que edita `target_year` y deja la declaración intacta, comprobando que su
línea no aparece en el diff.

### Alcance confirmado con Pablo el 2026-09-07

Frente a las cuatro preguntas de diseño planteadas antes de escribir
código:

- **`hard_constraints` y `superseded_decisions`, totalmente editables**
  (no solo lectura, que era la recomendación inicial). Decisión de Pablo:
  "no creo que pase nada por dejarme editar si yo sé lo que me hago".
  `hard_constraints` se edita como lista de texto libre igual que
  `pending_decisions`, con `min_length=1` en el modelo -protege solo
  contra vaciarla entera por accidente, no restringe qué se escribe en
  ella-. `superseded_decisions` se edita con CRUD completo: añadir,
  editar, quitar filas de `{clave, texto}`.
- **`disqualifying_conditions`: añadir filas y editar su `rule`, sin
  borrar ni reordenar.** Casado por `id` -texto libre, no vocabulario de
  código-; el campo extra de cada fila (`evaluable_from_posting`/
  `affects`) no lo gestiona el formulario y se enseña de solo lectura.
- **Pestañas en `/perfil`, sin cambiar de URL**, reutilizando el patrón de
  "selector arriba" que `docs/APP_SCREENS.md` documenta para Pipeline/
  CVs/Stats -aunque esa nota hablaba de vistas del mismo dato, no de tres
  formularios de tres ficheros distintos; se adoptó igual porque es el
  vocabulario visual que ya existe y no había motivo para inventar uno
  nuevo-.
- **`_yaml()` compartida**, ver el hallazgo de arriba.

### El mecanismo: `preferences.py` y `constraints.py`

Mismo patrón que `objectives.py` -`current`/`prepare`/`write`, revalida el
documento entero tras aplicar la edición-. Lo específico de cada fichero:

- **`preferences.py`** no tiene ninguna estructura nueva: nueve claves,
  todas escalares, pares de flujo (`intended_duration_years`,
  `current_living_costs_monthly_eur`, mismo patrón que
  `expected_tenure_years` de M0) o texto plegado con `set_folded_if_changed`.
- **`constraints.py`**:
  - `_apply_disqualifying_conditions` casa cada edición por `id` contra
    las filas existentes -un `dict` de `id -> CommentedMap`-, muta `rule`
    en su sitio con `set_folded_if_changed`, y añade un `CommentedMap`
    nuevo (`id` + `rule` en `FoldedScalarString`) para cualquier `id` que
    no exista todavía. Un `id` que el envío no traiga se queda como
    estaba: sin borrado, a propósito.
  - `_apply_superseded_decisions` opera sobre el `CommentedMap` real del
    documento: borra las claves que ya no estén en el envío, muta en su
    sitio (`set_folded_if_changed`) las que sigan y cambien de texto, y
    añade las nuevas al final. Nunca reconstruye el mapa entero -eso fue
    justo lo que el experimento de arriba descartó, porque reflowaría el
    texto de toda entrada aunque no hubiera cambiado-. Como asignar a una
    clave existente no cambia su posición en un `CommentedMap`, el orden
    de las claves que sobreviven se conserva solo, sin necesitar un paso
    de reordenar aparte.
  - `EditableConstraints.superseded_decisions` acepta tanto la lista de
    pares `{key, text}` que manda el formulario como el mapa que trae el
    YAML real -un `field_validator(mode="before")` convierte el segundo
    al primero-, porque `current()` valida el documento tal cual sale de
    `ruamel` y el formulario valida y manda la otra forma.

### El formulario: pestañas y filas dinámicas

`PerfilTabs.tsx` mantiene qué pestaña está activa en estado de React, sin
tocar la URL; cada formulario (`ObjectivesForm`, `PreferencesForm`,
`ConstraintsForm`) sigue siendo dueño de su propio estado y de su propio
`useActionState`, así que cambiar de pestaña no descarta un diff a medias
de otra -solo desmonta el formulario que deja de verse-.

`PreferencesForm` no tiene ninguna dificultad nueva: son los mismos
campos controlados que `ObjectivesForm` ya usaba, multiplicados. Las
filas dinámicas de `ConstraintsForm` sí lo son:

- **`disqualifying_conditions`**: `id` es de **solo lectura** en una fila
  existente -un input de texto libre ahí permitiría "renombrar" un `id`
  sin querer, que en el backend equivale a dejar la fila vieja intacta y
  crear una nueva duplicada, porque el casado es por `id`-. Solo la fila
  de "añadir condición nueva", al final, tiene un campo de identificador.
- **`superseded_decisions`**: clave y texto son editables en cualquier
  fila, con un botón de quitar por fila y uno de añadir al final -CRUD
  completo, sin el mismo riesgo de duplicado porque aquí no hay ninguna
  otra pantalla que dependa de que una clave se mantenga estable-.
- Las dos listas viajan al servidor como JSON en un campo oculto
  (`disqualifying_conditions_json`, `superseded_decisions_json`) en vez de
  como campos de `FormData` indexados: son de longitud variable, y
  serializar el estado de React que ya se mantiene es más simple y menos
  frágil que reconstruir un array a partir de claves `dq_id_0`, `dq_id_1`,
  etc.

### Fixtures y verificación

Fixtures nuevos, con datos inventados: `tests/fixtures/data_repo_write/config/preferences.yaml`
y `.../constraints.yaml`, mismas nueve claves que los ficheros reales
-comprobado contra `career-strategy` el 2026-09-07-, `disqualifying_conditions`
con un elemento `evaluable_from_posting` y otro `affects` a propósito,
como el real.

**Trampa encontrada al verificar en el navegador:** el remoto de git local
que hace de "GitHub" en desarrollo (`.dev-data/repo-write-remote.git`) ya
estaba sembrado desde M0, con la forma vieja de los fixtures. `make
seed-data-repo-write` solo siembra una vez -`if [ ! -d ... ]`-, así que la
API tiraba un 500 (`FileNotFoundError`) hasta borrar `.dev-data/` a mano y
dejar que `make up` lo resembrara. No es un bug: es el precio de que el
seed sea idempotente a propósito. Cualquier sesión que amplíe el fixture
de escritura tendrá que hacer lo mismo.

Verificado en esta máquina el 2026-09-07: `make check` limpio (364 tests
API -28 nuevos de `preferences`/`constraints`/`yaml_style`, más el de
regresión de `objectives`- + 17 web), `make e2e` con los 20 tests en verde
-incluidos los 3 nuevos de `perfil.spec.ts`: alternar pestañas sin cambiar
de URL, editar una preferencia de punta a punta, y añadir a la vez una
condición descalificante y una decisión sustituida-, y el mecanismo
comprobado a mano contra el stack de Compose real por `curl`
(`GET`/`preferences`, `GET`/`constraints`) tras resembrar el remoto local.

**Sin verificar, y no se puede desde aquí:** lo mismo que M0 -la deploy
key de verdad y el directorio en la VM de producción-, sin cambios desde
entonces.

## 2026-09-07 — M2, el banco de bullets y el contenido de variantes de rol

### La investigación confirmó los tamaños y corrigió el plan de "reutilizar"

`cv/content/professional_bullet_bank.yaml` (260 líneas, 13 bullets) y
`cv/content/role_variant_content.yaml` (107 líneas, 5 variantes) seguían
sin tocarse desde el 2026-08-13/14 y con la forma exacta que el troceo
daba por hecha. `config/cv_variants.yaml` (179 líneas) tampoco había
cambiado desde entonces.

Lo que **no** se sostuvo fue "reutilizar `src/cv_builder/models.py`" tal
cual proponía `NEXT_SESSION.md`. `cv-builder` (el generador de CI) y
`futuro-api` (esta API) son dos paquetes Python independientes -
`pyproject.toml`/`uv.lock` propios, sin `tool.uv.sources` que los enlace,
y el `Dockerfile` de `api` no copia `src/cv_builder` a su imagen-. Prueba
de ello: `data_repo/loader.py` (el lado de lectura del scoring) ya define
su **propio** `Bullet`, distinto del de `cv_builder`, para el mismo
concepto. Añadir `cv-builder` como dependencia de `futuro-api` habría
acoplado el ciclo de vida de dos paquetes que se despliegan por separado,
por una lógica de validación que cabe en ~30 líneas sin dependencias de
framework. **Decisión: portar, no importar.** `data_repo_write/claim_language.py`
copia `validate_contribution_language`/`_phrase_and_prefix` de
`cv_builder/claim_rules.py`, con un comentario que explica el porqué y
deja constancia de que una edición del original no se propaga sola.

### La validación cruzada: `config/cv_variants.yaml` se lee, no se edita

`config/cv_variants.yaml` es M3, no M2. Sus `claim_rules` se leen de
solo lectura del mismo clon de escritura ya sincronizado por
`pull --rebase` -sin clon nuevo, sin tocar `git_ops.py`-, con un modelo
Pydantic mínimo (`ClaimRulesForValidation`, solo
`professional_contribution_language.{allowed, blocked_without_specific_confirmation}`).
Se valida **todo** bullet cuyo `(evidence_status, cv_usage)` final sea
`(verified, eligible_with_internal_policy_check)` -no solo los que hoy
estén en el `candidate_bullet_priority` de alguna variante, a diferencia
de `cv_builder.build.resolve_variant`-, porque revalidar el documento
entero tras aplicar la edición es la misma disciplina que ya aplican
`objectives.py`/`preferences.py`/`constraints.py`.

Hallazgo de paso: el propio `professional_bullet_bank.yaml` trae un
bloque `policy.allowed_contribution_verbs`/`blocked_ownership_verbs` con
un vocabulario parecido pero no idéntico al de `cv_variants.yaml`
(`participated_in` frente a `participated_in_development`). Ningún
código -ni `claim_rules.py` ni `build.py`- lee nunca ese bloque: la
validación real siempre corre contra `cv_variants.yaml`. `policy` se
trata en M2 como bloque fijo, sin editar, transportado tal cual.

### Dos hallazgos nuevos de `ruamel.yaml`, distintos de los de M0/M1

Investigar con un fixture sintético que incluyera las formas difíciles
del fichero real -mismo hábito que corrigió el bug de M1- sacó a la luz
dos bugs de round-trip que no se habían visto porque ningún fichero
anterior los tenía:

- **Un `null` explícito se volvía a escribir en blanco.** `project_id: null`
  se convertía en `project_id:` con la sola secuencia cargar→volcar, **sin
  tocar nada** -comprobado byte a byte contra `professional_bullet_bank.yaml`
  real-. El representador de `None` por omisión de `ruamel` en modo
  *round-trip* no reproduce el estilo `null` del nodo original. Corregido
  registrando un representador propio en `yaml_style.data_repo_yaml()`
  (`tag:yaml.org,2002:null` / texto `null`), compartido por los cuatro
  módulos de fichero.
- **Un escalar plano de una sola línea física por encima de 80 caracteres
  se partía en dos al volcar**, sin tocarlo -`role_variant_content.yaml`
  real tiene varias líneas de `skills.value` así-. Corregido ensanchando
  `yaml.width` a un valor generoso (100.000). Comprobado explícitamente
  que esto **no** rompe el round-trip de los campos plegados de los otros
  tres ficheros: `ruamel` no fuerza un re-envolvido al ancho nuevo,
  conserva los saltos de línea del escalar tal como se cargó mientras
  quepan bajo ese ancho.

Los cinco ficheros reales (`objectives.yaml`, `preferences.yaml`,
`constraints.yaml`, `professional_bullet_bank.yaml`,
`role_variant_content.yaml`) se comprobaron byte a byte tras el arreglo,
igual que `config/cv_variants.yaml` -de solo lectura en M2, pero que M3
heredará el mismo mecanismo-.

### Alcance confirmado con Pablo el 2026-09-07

- **Bullets: solo `text_en`, `evidence_status` y `cv_usage` son
  editables por fila.** `bullet_id` casa cada edición contra la fila
  existente -mismo criterio que `disqualifying_conditions.id` en M1-; el
  resto (`bullet_type`, `project_id`, `angle`, `confidentiality_status`,
  `role_variants`, `blocked_by`, `guardrail`) pasa intacto.
- **Alta sí, baja no.** Añadir un `bullet_id` nuevo crea una fila con
  valores por defecto seguros para los campos que el formulario no
  gestiona (`project_id: null`, `angle` = el propio `bullet_id`,
  `bullet_type: role_scope` -el único valor real que ya trae
  `project_id: null`-, `role_variants`/`blocked_by` vacíos) y **sin
  fabricar una `confidentiality_status`**: se deja `null`, en vez de
  inventar una confirmación de confidencialidad que nadie ha dado.
- **Las 5 claves de `variants` en `role_variant_content.yaml` son
  fijas.** Coinciden con `base_variants` de `config/cv_variants.yaml`
  (M3); esta rebanada no ofrece alta ni baja, solo edita
  `display_name`/`use_when`/`profile`/`skills` de las que ya hay. El
  envío tiene que declarar exactamente esas claves, ni más ni menos
  -comprobado en `role_variant_content.py`, no en el modelo, porque el
  modelo no conoce el fichero vigente-.
- **`evidence_status`/`cv_usage` pasan a ser vocabulario de código.**
  Ningún código lo exigía antes -solo se comparaban contra una constante
  cada uno-, pero un typo dejaría un bullet inalcanzable en silencio,
  igual que `RoleFamily`. Cerrados en `data_repo_write/vocabularies.py`:
  `evidence_status` con los cuatro valores que `profile/project_catalog.yaml`
  ya documenta para el mismo concepto (`candidate`/`verified`/
  `publishable`/`rejected`); `cv_usage` con los observados en el propio
  banco de bullets más `conditional` (`blocked`/`conditional`/
  `eligible_with_internal_policy_check`).

### `skills`: CRUD por posición, no por identificador

Sin clave estable que casar -a diferencia de `bullets`-, `_apply_skills`
en `role_variant_content.py` muta cada fila por posición: la fila `i`
existente se edita en su sitio si cambia, las de más se añaden al final,
las que sobran se quitan del final. Nunca se reemplaza la `CommentedSeq`
entera de una tacada: hacerlo, incluso con contenido casi idéntico,
perdía la línea en blanco que separaba una variante de la siguiente -el
mismo hallazgo de M1 sobre listas de nivel superior, aquí en una lista
anidada-. **Limitación conocida y sin resolver:** añadir una fila nueva sí
deja esa línea en blanco mal colocada -antes de la fila añadida en vez de
después-, porque `ruamel` no traslada el comentario de fin de bloque al
añadir un elemento. El YAML resultante es válido y el contenido correcto;
es una línea en blanco fuera de sitio, no un dato perdido, y no se
consideró que mereciera la complejidad de tocar `.ca.items` de `ruamel`
para un caso tan acotado.

### La pantalla: dos pestañas más, cinco en total

`/perfil` pasa a tener cinco pestañas -Objetivos, Preferencias,
Restricciones, Bullets, Variantes de rol-. `BulletBankForm` y
`RoleVariantsForm` siguen el mismo patrón que `ConstraintsForm`: filas de
largo variable viajan como JSON en un campo oculto
(`bullets_json`, `variants_json`), campos controlados -nunca
`defaultValue`-, un único `useActionState` con `intent=diff|commit`. Los
campos de una fila que se repiten entre bullets/variantes (`Texto de`,
`Estado de la evidencia`, `Perfil`) llevan además un `aria-label` con el
identificador de la fila -`Texto de invented_bullet_one`-, porque su
etiqueta visible sola no basta para que Playwright (o un lector de
pantalla) distinga una fila de otra.

La "revisión de redacción de las afirmaciones de estado" que pedía
`ARCHITECTURE.md` §14 se investigó de nuevo el 2026-09-07: las seis
afirmaciones (`deployed`, `delivering`, `operational`, `transformed`,
`reusable`, más la adopción de `work_data_review_workflow`) siguen
confirmadas el 2026-08-14 en `profile/project_audits/*.md`, y ese mismo
registro vive como prosa en `policy.status_claims_confirmed_2026_08_14`
del propio banco de bullets. Se enseña de solo lectura en la pestaña de
Bullets -un párrafo, sin botones-, sin construir ningún flujo editorial
nuevo, tal como pedía `NEXT_SESSION.md`.

### Fixtures y verificación

Fixtures nuevos, con datos inventados: `config/cv_variants.yaml` (de solo
lectura para M2, con `claim_rules` inventadas pero con la misma forma que
el real) y `cv/content/{professional_bullet_bank,role_variant_content}.yaml`
bajo `tests/fixtures/data_repo_write/` -dos bullets y dos variantes, no
trece y cinco: bastan para ejercitar el CRUD, la validación cruzada y la
regla de "claves fijas" sin necesitar el volumen real-.

Verificado en esta máquina el 2026-09-07: `make check` limpio (402 tests
API -38 nuevos de `bullet_bank`, `role_variant_content`, `claim_language`
y el router- + 17 web), `make e2e` con los 23 tests en verde -incluidos
los 3 nuevos de `perfil.spec.ts`: editar el texto de un bullet, añadir un
bullet nuevo, y editar el perfil de una variante-, y capturas de pantalla
de las dos pestañas nuevas revisadas a mano. El remoto de git local
(`.dev-data/repo-write-remote.git`) se volvió a resembrar tras ampliar el
fixture -mismo precio que M1 ya documentó-.

**Sin verificar, y no se puede desde aquí:** lo mismo que M0/M1 -la
deploy key de verdad y el directorio en la VM de producción-, sin
cambios desde entonces.
