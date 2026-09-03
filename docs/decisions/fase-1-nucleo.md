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
