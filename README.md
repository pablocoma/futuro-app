# futuro-app

Aplicación que convierte una oferta de trabajo en una candidatura lista para
enviar. 

Este repositorio es **público** y contiene solo código: sin datos personales,
sin evidencias, sin contenido de CV real, ni siquiera en fixtures de test. El
perfil, las evidencias, el contenido de CV y la configuración viven en el
repositorio privado `Futuro`, que esta aplicación clona y edita mediante una
deploy key.

## Estado

- **Fase 0.5** (generador de CVs, ejecutado en CI del repositorio
  privado) — cerrada 2026-09-03.
- **Fase 1** (núcleo: pegar oferta → extraer → puntuar → recomendar
  variante → descargar el PDF que CI construyó) — cerrada y **en
  producción** desde 2026-09-05.
- **Fase 2** (perfil editable: los ocho YAML del repositorio privado,
  con diff en pantalla y confirmación antes de cada commit) — cerrada en
  código el 2026-09-08. Pendiente de aprovisionar a mano en producción:
  la deploy key de lectura-escritura (`docs/deployment.md` §10).
- **Fase 3** (pipeline y seguimiento) — en curso desde 2026-09-08, en
  ocho rebanadas. A diferencia de Fase 2, no toca el repositorio privado.
  Rebanada 1 (modelo de estados de candidatura, `offer_status_events`)
  cerrada el 2026-09-08.

Qué se integró y por qué en cada fase: `docs/decisions/fase-<n>-*.md`
(un fichero por fase, ampliado en cada rebanada, sin podar nunca). Estado
operativo del día a día y troceo de la fase en curso: `NEXT_SESSION.md`,
que sí se reescribe en cada cierre y no acumula el detalle que ya vive en
`docs/decisions/`.

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

Para editar el perfil (`/perfil`, Fase 2), la aplicación necesita además
su propio clon de **lectura-escritura**, distinto del anterior: `make up`
lo siembra solo con `make seed-data-repo-write`, un repo bare local en
`.dev-data/` que hace de "GitHub" en desarrollo, así que tampoco hace
falta una deploy key real ni tocar el repositorio privado para probar el
mecanismo. Apuntar al `Futuro` real es `DATA_REPO_WRITE_REMOTE` en
`.env`, con su propia clave montada a mano (`docker-compose.override.yml`).

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
