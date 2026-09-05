# futuro-app

Aplicación que convierte una oferta de trabajo en una candidatura lista para
enviar. 

Este repositorio es **público** y contiene solo código: sin datos personales,
sin evidencias, sin contenido de CV real, ni siquiera en fixtures de test. El
perfil, las evidencias, el contenido de CV y la configuración viven en el
repositorio privado `Futuro`, que esta aplicación clona y edita mediante una
deploy key.

## Estado

Fase 0.5 cerrada el 2026-09-03: el generador de variantes de CV en
Python/Jinja2 (paquete `cv_builder`) y el `Dockerfile` con Tectonic y caché de
paquetes precalentada. Ver `src/cv_builder/README.md` para el uso del CLI y el
contrato que debe cumplir la plantilla del maestro. El workflow `build-cvs` de
GitHub Actions del repositorio privado `Futuro` ya lo invoca para regenerar y
compilar las cinco variantes base.

En curso, Fase 1 — el núcleo de la aplicación: pegar texto de una oferta →
clasificar con LLM → scoring → recomendar variante → descargar el PDF que CI
construyó. Se entrega en cuatro rebanadas verticales (M0 a M3); troceo y
estado en `NEXT_SESSION.md`.

M0 (esqueleto) está cerrada: Compose con `caddy`, `api` (FastAPI + uv), `web`
(Next.js 16) y `postgres`, la API cerrada por omisión, OAuth de Google con
allowlist de un email, y CI en `dev`.

M1 (ingesta y extracción) está cerrada: pegar el texto de una oferta,
extraerla con el LLM en segundo plano y ver lo extraído con la evidencia de
cada campo al lado —la cita literal cuando consta, el razonamiento y la
confianza cuando se dedujo, «sin datos» cuando no aparece—. El LLM elige y
cita; el código valida en Python, degrada lo que el contrato manda degradar y
deja constancia de cada corrección. Con esto entran los seis servicios de la
arquitectura: `redis` y `worker` incluidos.

M2 (scoring y recomendación de variante) está cerrada: una oferta extraída se
puntúa sola contra el modelo de scoring del repositorio privado y se le
recomienda una de las cinco variantes de CV que ya existen. Aquí el principio
es distinto del de M1: **el LLM juzga y el código calcula**. El modelo pone la
nota de cada dimensión, la cita que la sostiene y el motivo; la media
ponderada, la renormalización, la cobertura, el cubo de cartera y el nivel de
esfuerzo los calcula Python, y el esquema de salida del modelo no tiene
siquiera dónde escribirlos. Una nota sin cita no entra: su dimensión queda
sin puntuar, y la pantalla lo enseña como un hueco rayado en vez de
ocultarlo. La puntuación es recalculable sin volver a llamar al modelo, y hay
un camino real para repuntuar el histórico recorriendo la base de datos.

M3 (entrega del PDF y dossier mínimo) está cerrada, y con ella **la Fase 1
entera**: con una oferta ya puntuada, se puede ver el PDF de cualquiera de
las variantes disponibles —leído de un clon de solo lectura del repositorio
privado—, confirmar una o cambiarla, y esa confirmación queda en su propia
fila en Postgres sin tocar la recomendación del modelo.

**En producción desde el 2026-09-05.** Cada merge a `main` despliega solo:
imágenes arm64 a GHCR, SSH a la VM de Oracle, el clon del repositorio de
datos, migraciones, comprobación de salud y rollback al tag anterior si
falla. Lo que hay que provisionar a mano —y las trampas que tiene— está en
`docs/deployment.md`; los valores concretos viven en el repositorio
privado, nunca aquí.

**Pendiente antes del próximo merge a `main`:** provisionar la deploy key de
solo lectura del repositorio de datos (`docs/deployment.md` §9); sin ella el
deploy se bloquea con un mensaje claro, en vez de desplegar a medias.

Siguiente: Fase 2, perfil editable — la primera que escribe en el
repositorio privado.

## Desarrollo local

```bash
cp .env.example .env      # los valores por defecto ya sirven
make up                   # → http://localhost:8080
make check                # lint, tipos y tests de los tres componentes
make e2e                  # smoke test contra el stack levantado
```

No se instala nada en el Mac: todo corre en Compose. `make help` lista el
resto de atajos. Con los valores de `.env.example`, `DEV_AUTH_BYPASS=true`
inyecta un usuario fijo y no hace falta cuenta de Google, y
`LLM_PROVIDER=stub` simula las extracciones a partir del propio texto
pegado, así que tampoco hace falta clave de OpenAI ni se gasta nada. Para
extraer de verdad, `LLM_PROVIDER=openai` con su clave y su modelo.

`make check` necesita el `postgres` de `make up` levantado: parte de los
tests comprueban constraints y triggers, que no existen en ningún otro
sitio.

Para puntuar y para servir el PDF de una variante, la aplicación lee el
modelo de scoring, la guía de variantes de CV y los propios PDF del
repositorio privado `Futuro`, montado de solo lectura en `/data/repo`. Por
omisión `DATA_REPO_HOST_PATH` apunta a un repositorio de
datos **sintético** que vive en este repositorio
(`services/api/tests/fixtures/data_repo/`): imita la forma del privado, no
comparte ni un dato con él y describe a una persona que no existe. Con eso,
un clon nuevo puntúa una oferta de punta a punta sin tener el privado
delante. Apuntarlo al de verdad es una línea en `.env`. Sin repositorio de
datos la aplicación funciona igual y lo único que falla es puntuar, con el
motivo a la vista en `/api/health` y en la pantalla.

Para repuntuar el histórico entero tras cambiar el modelo de scoring, sin
llamar al modelo:

```bash
docker compose exec worker python -m futuro_api.assessment.recompute
```

Las decisiones de arquitectura completas —stack, topología de repositorios,
servicios, ingesta de ofertas, fases de entrega— están documentadas en
`ARCHITECTURE.md` del repositorio privado `Futuro`. No se duplican aquí.

## Por qué está hecho así

`docs/decisions/` recoge, una entrada por fase, qué se integró y por qué:
decisiones de implementación y desviaciones deliberadas. Es un registro que
se acumula, distinto de `NEXT_SESSION.md` (estado operativo, se reescribe).

`docs/deployment.md` es la lista de lo que hay que provisionar a mano para
que el deploy pueda ejecutarse, y por qué cada pieza es como es.

## Reglas de trabajo

Ver `AGENTS.md`.
