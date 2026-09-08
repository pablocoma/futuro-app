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

## Cómo se trocea el trabajo

- Cada fase se entrega en rebanadas verticales, cada una funcionando de
  punta a punta y en su propia sesión de Claude Code. Una sesión debe
  terminar con holgura de contexto (en torno al 30-40% de uso, nunca al
  límite): trocea más fino cuando una rebanada es exploratoria -una
  decisión de modelo de datos, una superficie de UI nueva, una
  integración externa- y puedes mantenerla más grande cuando es mecánica
  y ya tiene precedente directo dentro del repositorio. El troceo se
  propone y se ajusta con Pablo; no es un contrato inamovible si la
  realidad no encaja al llegar a una rebanada concreta.
- Al empezar una rebanada, investiga el estado real de lo que se vaya a
  tocar -código de este repositorio, y `APP_SCREENS.md`/
  `ARCHITECTURE.md`/el contrato de datos del repositorio privado si
  aplica- antes de proponer nada. No des por buena una cifra, una forma
  de dato o un camino de código de memoria o de una sesión anterior:
  verifícalo. Propón el diseño concreto de esa rebanada y espera el
  visto bueno antes de escribir código.
- El prompt de traspaso a la siguiente sesión debe ser breve: qué
  rebanada toca y qué investigar antes de proponer diseño. No repitas
  contenido que ya esté escrito en `NEXT_SESSION.md` o en este documento;
  remite a ellos.

## Documentación operativa: no la dupliques entre ficheros

- `NEXT_SESSION.md` es **solo el estado operativo actual y el troceo de
  la fase en curso**: qué fase/rebanada está cerrada (una línea, con
  referencia a `docs/decisions/`), qué sigue, y cabos sueltos de
  producción todavía abiertos. **Se reescribe en cada cierre de
  rebanada, no acumula**: si al editarlo te encuentras repitiendo el
  detalle de una rebanada ya cerrada, pódalo -ese detalle ya vive en
  `docs/decisions/`- en vez de dejarlo también ahí. Un `NEXT_SESSION.md`
  que crece sin límite es la señal de que esta regla no se está
  siguiendo.
- Al cerrar una rebanada, añade o amplía en `docs/decisions/` el fichero
  de esa **fase** (`fase-<n>-<slug>.md`, uno por fase y no por rebanada,
  ver `ARCHITECTURE.md` del repositorio privado para la numeración; cada
  rebanada es una sección fechada nueva dentro del mismo fichero)
  explicando **qué se integró y por qué**: decisiones de implementación,
  desviaciones deliberadas respecto a lo esperado y alcance dejado fuera
  a propósito. Es distinto de `NEXT_SESSION.md`: ese archivo es estado
  operativo y se reescribe; `docs/decisions/` es un registro que se
  acumula y no se poda. Este repositorio documenta aquí solo decisiones
  de código; el repositorio privado `Futuro` mantiene su propio
  `docs/decisions/` (o equivalente) para las decisiones de su mitad
  (datos, plantillas, workflows de CI).
- El hook de arranque de sesión ya vuelca `README.md` y
  `NEXT_SESSION.md` enteros en el contexto: no los releas con la
  herramienta de lectura al empezar salvo que sospeches que están
  desactualizados o necesites confirmar algo tras una edición propia
  dentro de la misma sesión. Si un fichero de `docs/decisions/`
  acumulado ya tiene varias rebanadas, basta con leer su sección más
  reciente -el índice de secciones del propio fichero dice si hace falta
  alguna anterior concreta-, no el fichero entero.
- `README.md` mantiene solo un resumen de una o dos frases por fase en su
  sección de Estado, con referencia a `docs/decisions/`: no es una
  narración ni repite lo que ya cuenta `NEXT_SESSION.md`.

## Calidad

- Las recomendaciones deben explicar sus supuestos y sus trade-offs.
- Al arrancar un componente nuevo dentro de este repositorio (un servicio, un
  módulo con su propio ciclo de vida), su harness se configura como parte del
  bootstrap, no después.
