# Traspaso a la siguiente sesión

Última actualización: 2026-09-03.

Este archivo contiene el estado operativo del proyecto. Las reglas duraderas
están en `AGENTS.md`; no deben duplicarse aquí.

## Estado comprobado

- Repositorio creado el 2026-09-02 como público bajo la cuenta `pablocoma`.
  Bootstrap: `README.md`, `AGENTS.md`, `CLAUDE.md`, `.gitignore` y el harness
  de Claude Code. `dev` existe desde el commit fundacional; el trabajo se
  hace ahí.
- Las decisiones de arquitectura están cerradas en `ARCHITECTURE.md` del
  repositorio privado `Futuro`, no duplicadas aquí.

### Fase 0.5 — mitad de `futuro-app` (esta sesión)

Construido, con harness completo desde el primer commit del componente:
`pyproject.toml`/`uv.lock` (Python 3.13 vía `uv`), el paquete
`src/cv_builder/` (modelos, `claim_rules`, `build`, `render`, `cli` — uso y
contrato de la plantilla del maestro en `src/cv_builder/README.md`), 22
tests contra fixtures sintéticas propias en `tests/`, y
`docker/Dockerfile` (Tectonic 0.17.0 con caché precalentada). Verificado en
esta máquina: `uv sync`, `ruff`, `mypy --strict`, `pytest` (22 passed),
`docker build` y un smoke test completo dentro del contenedor
(`cv-builder build` + `tectonic` compilando a PDF sin fallos).

El porqué de cada decisión de implementación (delimitadores Jinja2,
normalización de verbos de contribución, por qué el README generado no
lleva datos personales, qué se dejó fuera de alcance a propósito) está en
`docs/decisions/fase-0.5-workflow-de-cvs.md`, no aquí.

Commiteado en `dev` (local, sin `push` todavía).

## Siguiente objetivo: completar Fase 0.5 en el repositorio privado `Futuro`

Falta, en `Futuro` (no aquí — su propio traspaso pide que ese trabajo se
haga en una sesión con `Futuro` como raíz):

1. Convertir el `.tex` maestro (`cv/master/`) a una plantilla Jinja2
   (`\VAR{}`/`\BLOCK{}`) que cumpla el contrato de
   `src/cv_builder/README.md` (de `futuro-app`): `\VAR{profile}`, un bucle
   `\BLOCK{for bullet in role_bullets}` dentro del `\entry` del puesto
   actual, y un bucle `\BLOCK{for row in skill_rows}` en Technical Skills.
   El resto del documento queda literal.
2. Montar el workflow `build-cvs` de GitHub Actions en `Futuro`, disparado
   por cambios en `cv/content/professional_bullet_bank.yaml`,
   `cv/content/role_variant_content.yaml`, `config/cv_variants.yaml` o el
   maestro, que use la imagen de `docker/Dockerfile` de `futuro-app` para
   generar y compilar las cinco variantes y comitear `.tex` + PDF de vuelta.
3. Regenerar las cinco variantes reales: están desactualizadas desde que se
   autorizaron los trece bullets el 2026-08-13 (se construyeron con cinco).

Después de eso, Fase 0.5 queda cerrada y empieza la Fase 1 (núcleo:
ingesta de ofertas → scoring → recomendación de variante), ya en
`futuro-app`.
