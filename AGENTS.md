# Instrucciones del repositorio

## Propósito

Este repositorio contiene el código de la aplicación que ayuda a Pablo Coma
Valbuena a gestionar su transición profesional durante 2026. Es **público**.

Los datos —perfil, evidencias, contenido de CV, configuración, oportunidades—
viven en el repositorio privado `Futuro`. Esta aplicación los lee, valida y
escribe ahí; no los duplica en este repositorio.

## Principios

- Cero datos personales en este repositorio, en ningún commit, ni siquiera de
  ejemplo. Los tests usan un repo sintético generado en `tests/fixtures/`, no
  una copia del repositorio privado.
- El repositorio privado `Futuro` es la fuente de verdad del perfil. La app
  hace `git pull --rebase` antes de escribir, valida contra el modelo Pydantic
  del fichero, y solo hace commit si la validación pasa.
- Las decisiones de arquitectura están cerradas en `ARCHITECTURE.md` del
  repositorio privado. No las dupliques aquí ni las relitigues sin motivo
  nuevo; referencia esa fuente.
- El generador de CV valida las `claim_rules` de `config/cv_variants.yaml` en
  código Python, no confiando en ningún modelo: solo entran bullets con
  `evidence_status: verified` y `cv_usage: eligible_with_internal_policy_check`,
  el verbo de contribución se valida contra la lista permitida, y las
  `fixed_sections` no son editables por ningún camino.
- El LLM elige y cita; no redacta el CV ni inventa logros.
- El trabajo se hace en la rama `dev`. `main` queda protegida y desplegable.

## Calidad

- Mantén `README.md` y `NEXT_SESSION.md` actualizados después de cambios
  estructurales.
- Al comenzar una nueva sesión, lee `README.md` y `NEXT_SESSION.md` antes de
  proponer o ejecutar cambios. Al cerrar un hito, actualiza `NEXT_SESSION.md`
  con el estado comprobado y el siguiente objetivo.
- Las recomendaciones deben explicar sus supuestos y sus trade-offs.
- Al arrancar un componente nuevo dentro de este repositorio (un servicio, un
  módulo con su propio ciclo de vida), su harness se configura como parte del
  bootstrap, no después.
