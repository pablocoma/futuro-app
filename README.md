# futuro-app

Aplicación que convierte una oferta de trabajo en una candidatura lista para
enviar. 

Este repositorio es **público** y contiene solo código: sin datos personales,
sin evidencias, sin contenido de CV real, ni siquiera en fixtures de test. El
perfil, las evidencias, el contenido de CV y la configuración viven en el
repositorio privado `Futuro`, que esta aplicación clona y edita mediante una
deploy key.

## Estado

Fase 0.5 — mitad de `futuro-app` completa: el generador de variantes de CV en
Python/Jinja2 (paquete `cv_builder`) y el `Dockerfile` con Tectonic y caché de
paquetes precalentada. Ver `src/cv_builder/README.md` para el uso del CLI y
el contrato que debe cumplir la plantilla del maestro. Queda pendiente, en el
repositorio privado `Futuro`, convertir el maestro real a esa plantilla
Jinja2 y montar el workflow `build-cvs` de GitHub Actions que invoca este
generador — detalle en `NEXT_SESSION.md`.

Las decisiones de arquitectura completas —stack, topología de repositorios,
servicios, ingesta de ofertas, fases de entrega— están documentadas en
`ARCHITECTURE.md` del repositorio privado `Futuro`. No se duplican aquí.

## Por qué está hecho así

`docs/decisions/` recoge, una entrada por fase, qué se integró y por qué:
decisiones de implementación y desviaciones deliberadas. Es un registro que
se acumula, distinto de `NEXT_SESSION.md` (estado operativo, se reescribe).

## Reglas de trabajo

Ver `AGENTS.md`.
