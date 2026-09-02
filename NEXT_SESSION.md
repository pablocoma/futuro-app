# Traspaso a la siguiente sesión

Última actualización: 2026-09-02.

Este archivo contiene el estado operativo del proyecto. Las reglas duraderas
están en `AGENTS.md`; no deben duplicarse aquí.

## Estado comprobado

- Repositorio creado el 2026-09-02 como público bajo la cuenta `pablocoma`.
- Contiene solo el bootstrap: `README.md`, `AGENTS.md`, `CLAUDE.md`,
  `.gitignore` y el harness de Claude Code (`.claude/settings.json` con hooks
  de sesión y denegación de `git add -A`/`git add .`).
- Sin código todavía. El bootstrap se hizo sobre `main` por ser el commit
  fundacional; `dev` ya existe, creada desde ese mismo commit, y es donde se
  desarrolla la Fase 0.5.
- Las decisiones de arquitectura están cerradas en `ARCHITECTURE.md` del
  repositorio privado `Futuro`, no duplicadas aquí.

## Siguiente objetivo: Fase 0.5

Construir el generador de variantes de CV en Python con Jinja2, sustituyendo
al script Ruby archivado en el repositorio privado
(`archive/legacy/generate_cv_variants.rb`), que:

1. Genere el `.tex` de cada variante base a partir de una plantilla del
   maestro.
2. Aplique las `claim_rules` de `config/cv_variants.yaml` en código Python.
3. Se compile con un `Dockerfile` que instale Tectonic y precaliente su caché
   de paquetes con un documento de muestra, para que la compilación real sea
   offline.

Detalle completo en la sección "7. Selección de CV" y "14. Fases de entrega"
de `ARCHITECTURE.md` (repositorio privado). El trabajo de esta fase se hace en
`dev`.
