# futuro-app

Aplicación que convierte una oferta de trabajo en una candidatura lista para
enviar. Código de la aplicación de Pablo Coma Valbuena para su transición
profesional durante 2026.

Este repositorio es **público** y contiene solo código: sin datos personales,
sin evidencias, sin contenido de CV real, ni siquiera en fixtures de test. El
perfil, las evidencias, el contenido de CV y la configuración viven en el
repositorio privado `Futuro`, que esta aplicación clona y edita mediante una
deploy key.

## Estado

Fase 0.5 en marcha: portar a Python con Jinja2 el generador de variantes de CV
(hoy un script Ruby archivado en el repositorio privado), y montar el
`Dockerfile` con Tectonic que compila cada variante a PDF con la caché de
paquetes precalentada.

Las decisiones de arquitectura completas —stack, topología de repositorios,
servicios, ingesta de ofertas, fases de entrega— están documentadas en
`ARCHITECTURE.md` del repositorio privado `Futuro`. No se duplican aquí.

## Reglas de trabajo

Ver `AGENTS.md`.
