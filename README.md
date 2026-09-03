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

M0 (esqueleto) está construido y verificado en local: Compose con `caddy`,
`api` (FastAPI + uv), `web` (Next.js 16) y `postgres`, `GET /api/health` con
su página, OAuth de Google con allowlist de un email, CI en `dev` y el
workflow de deploy. El deploy a la VM de Oracle está escrito y sin estrenar:
la VM, el dominio y el cliente OAuth se provisionan a mano siguiendo
`docs/deployment.md`.

M1 (ingesta y extracción) está en curso: las tablas de las capas `capture` y
`extraction` del contrato de datos, el módulo de LLM aislado con registro de
coste por llamada, y las reglas que validan en Python lo que el modelo
devuelve. Quedan la cola, los endpoints y la pantalla de la oferta.

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
