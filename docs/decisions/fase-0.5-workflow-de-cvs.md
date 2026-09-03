# Fase 0.5 — El workflow de CVs

Ver `ARCHITECTURE.md` (repositorio privado `Futuro`) §7 y §14 para el
alcance cerrado de esta fase. Este documento recoge, en este repositorio,
solo las decisiones de implementación tomadas al construir la mitad de
`futuro-app`: el paquete `src/cv_builder/` y `docker/Dockerfile`. La mitad
de `Futuro` (convertir el maestro real a plantilla Jinja2, montar el
workflow `build-cvs`) debe registrar sus propias decisiones en el
`docs/decisions/` (o equivalente) de ese repositorio, no aquí.

## 2026-09-03 — Generador Python/Jinja2 (sustituye al script Ruby)

**Contexto.** El generador anterior
(`archive/legacy/generate_cv_variants.rb`, en `Futuro`) parcheaba con regex
el `.tex` maestro ya compilado y vivía en el repo privado, donde podía
hardcodear texto personal sin problema. Al mover el generador al repo
público había que resolver varias cosas que el Ruby no necesitaba resolver.

**Decisión: delimitadores Jinja2 no estándar (`\VAR{...}`, `\BLOCK{...}`).**
Los delimitadores por defecto de Jinja2 (`{{ }}`, `{% %}`, `{# #}`) chocan
con el propio maestro: sus macros LaTeX se definen como
`\newcommand{\entry}[5]{\textbf{#1}...}`, y la secuencia literal `{#`
(la `{` de `\textbf{` seguida del `#1`) se interpreta como inicio de un
comentario Jinja2 y rompe el parseo. La solución — delimitadores tipo
`\VAR{}`/`\BLOCK{}` — es la misma que usa Sphinx para generar LaTeX con
Jinja2; evita cualquier colisión porque esas secuencias no existen en LaTeX
normal. Contrato completo en `src/cv_builder/README.md`.

**Decisión: verbo de contribución permitido/bloqueado, normalizado
genéricamente.** Los dos ficheros de origen no comparten vocabulario para
el mismo verbo: el banco de bullets usa el id `participated_in`;
`config/cv_variants.yaml` usa `participated_in_development`. En vez de
elegir uno a mano (o hardcodear una lista de frases en Python, que
duplicaría la config y se desincronizaría), `claim_rules.py` convierte
cada id a frase (`_` → espacio) y compara tanto la frase completa como sus
dos primeras palabras contra el inicio del texto del bullet. Así ambos
ficheros quedan satisfechos por el mismo bullet sin acoplar el validador a
uno de los dos.

**Decisión: verbo bloqueado por palabra completa, no subcadena.** Un primer
borrador buscaba la subcadena del verbo bloqueado (p. ej. `"led"`) en el
texto con `in`. Eso da falsos positivos: `"led"` aparece dentro de
`"scheduled"` o `"knowledge"`. Se cambió a una búsqueda con límites de
palabra (`\bled\b`) para que solo dispare sobre el verbo real.

**Decisión: el `README.md` por variante no hardcodea el proyecto público.**
El Ruby original sí lo hacía (nombre y descripción de
`Concept Bottleneck Models on Fashion-MNIST` en su heredoc), pero vivía en
el repo privado, donde eso no es un problema. Portarlo tal cual al repo
público habría metido datos personales en código versionado, violando el
principio de "cero datos personales en este repositorio". El README
generado por `cv_builder` documenta solo lo que el propio pipeline decide
(perfil, bullets seleccionados, skills, roles objetivo) y una nota genérica
de que el resto del maestro no cambia.

**Decisión: `selected_project` queda fuera de esta fase.** Está listado
como `tailorable` en `config/cv_variants.yaml`, pero seleccionarlo
requeriría leer `profile/project_catalog.yaml`, una fuente que
`ARCHITECTURE.md` no menciona en los pasos de construcción de Fase 0.5. El
generador deja esa sección — junto con identidad, empresa/fechas,
educación, Languages y Awards — como LaTeX literal sin variables Jinja2 en
la plantilla del maestro: no hay ningún camino de datos que pueda tocarlas,
así que las `fixed_sections` quedan inmodificables por construcción y no
por una comprobación en tiempo de ejecución.

**Decisión: build atómico.** `build_all()` resuelve y valida todas las
variantes antes de escribir la primera a disco. Un fallo en cualquier
variante (bullet no elegible, `bullet_id` desconocido, verbo bloqueado)
aborta el build entero sin dejar una construcción a medias — mismo
contrato que el `exit(1)` del Ruby original.

**Decisión: Tectonic 0.17.0 fijado por sha256, no la última versión en
build-time.** El `Dockerfile` descarga el binario estático de GitHub
Releases (`aarch64-unknown-linux-musl` o `x86_64-unknown-linux-musl` según
`$TARGETARCH`) y verifica su hash contra un valor fijado en el propio
`Dockerfile`. Fijar versión y hash hace el build reproducible y evita que
una build futura falle o cambie de comportamiento sin más contexto que "se
publicó una versión nueva de Tectonic".

**Decisión: dependencias mínimas.** CLI con `argparse` (stdlib) en vez de
`click`/`typer`: un único subcomando no lo justifica. Lectura de YAML con
`pyyaml` (`safe_load`) en vez de `ruamel.yaml`: este generador solo lee
configuración, nunca la reescribe — el round-trip que preserva comentarios
y orden de claves es necesario para la Fase 2 (perfil editable), no para
esto.

## Verificación

`uv sync`, `ruff check`/`ruff format --check`, `mypy --strict src`,
`pytest` (22 tests contra fixtures sintéticas propias, sin ningún dato de
`Futuro`), `docker build`, y un smoke test manual dentro del contenedor:
`cv-builder build` sobre los fixtures seguido de `tectonic` compilando el
`.tex` resultante a PDF sin errores.
