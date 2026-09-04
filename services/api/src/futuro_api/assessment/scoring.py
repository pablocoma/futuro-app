"""La aritmética de la capa `assessment`. Aquí no hay ningún modelo.

Todo este módulo es una función pura: entran las notas y los estados de
filtro que ya validó `rules.py`, y salen la media ponderada, la cobertura,
el cubo de cartera y el nivel de esfuerzo. No hay ninguna llamada al LLM y
no puede haberla, y eso es lo que hace que `assessment` sea recalculable:
`recompute.py` llama exactamente a esto sobre notas ya guardadas.

## Por qué hay umbrales escritos aquí

`config/scoring_model.yaml` no expresa sus reglas en forma legible por
máquina. `realistic: probabilidad high y valor >= 3.0` es prosa, y
`full.when: valor >= 4.0 y ningún filtro en fail` también. Lo que sí es
legible por máquina —los pesos, las anclas, la escala, los nombres de
bandas, cubos y niveles, `minimum_coverage` y `evaluation_order`— se lee del
YAML y no se repite aquí.

Los predicados y sus dos umbrales están copiados a mano, con su fecha. Es
exactamente lo que hace `llm/cost.py` con la tabla de tarifas del
proveedor, y por la misma razón: la fuente es prosa para humanos. Las tres
defensas son las mismas que allí:

1. el cargador exige que el YAML declare exactamente los cubos y niveles
   que este módulo sabe calcular, así que una regla nueva no se queda sin
   asignar en silencio;
2. cada fila de assessment guarda el `sha256` del YAML con el que se
   puntuó, así que un umbral mal copiado se localiza y se repuntúa;
3. repuntuar no cuesta una llamada al modelo.

Cuando `portfolio_assignment` y `output.effort_tier` pasen a forma legible
por máquina en el repositorio privado, estos umbrales se borran y se leen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from futuro_api.assessment import vocabularies as vocab
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.data_repo.models import ScoringModel

logger = logging.getLogger(__name__)

# Umbrales leídos a mano de `config/scoring_model.yaml`, de
# `portfolio_assignment` y de `output.effort_tier`. Copiados el 2026-09-04 de
# la versión 1 y revisados el 2026-09-05 contra la versión 2, que no los
# cambió: lo que la v2 cambió fueron los predicados que los usan.
# Cambiarlos allí obliga a cambiarlos aquí; el hash del YAML que se guarda en
# cada fila es lo que permite saber después qué filas se puntuaron con qué
# texto.
VALUE_FLOOR = Decimal("3.0")
VALUE_FULL_EFFORT = Decimal("4.0")

# Dos decimales en el valor, tres en la cobertura. El primero porque es lo
# que `APP_SCREENS.md` pinta («3.19», número grande sin escala) y lo que la
# columna NUMERIC(3,2) guarda; la segunda porque un 0,5 y un 0,499 deciden
# cosas distintas y con dos decimales serían el mismo número.
_VALUE_PLACES = Decimal("0.01")
_COVERAGE_PLACES = Decimal("0.001")


# El reparto por banda de `portfolio_assignment`. `very_low` comparte cubo
# con `low` desde el 2026-09-05: no puede tener uno propio, porque los cinco
# nombres de `PortfolioBucket` son vocabulario de código y el cargador
# prohíbe ampliarlos.
BUCKET_OF_BAND: dict[data_vocab.ProbabilityBand, data_vocab.PortfolioBucket] = {
    data_vocab.ProbabilityBand.HIGH: data_vocab.PortfolioBucket.REALISTIC,
    data_vocab.ProbabilityBand.MEDIUM: data_vocab.PortfolioBucket.REALISTIC_STRETCH,
    data_vocab.ProbabilityBand.LOW: data_vocab.PortfolioBucket.ASPIRATIONAL,
    data_vocab.ProbabilityBand.VERY_LOW: data_vocab.PortfolioBucket.ASPIRATIONAL,
}


@dataclass(frozen=True)
class ScoredDimension:
    """Una dimensión ya resuelta, puntuada o no.

    `weight` y `anchor` se guardan con la fila y no se releen del YAML al
    pintar. Es lo que hace reproducible el dibujo: la barra de una oferta
    vieja se pinta con el peso que produjo su nota, no con el de hoy, y el
    texto del ancla es el que justificaba esa nota entonces.

    Una dimensión sin puntuar tiene `score`, `citation` y `anchor` nulos y
    `unscored_reason` con el motivo. No es una lista aparte: `unscored`
    **es** esta fila con la nota vacía, así que no puede contradecir a las
    notas.
    """

    name: str
    weight: int
    score: int | None
    citation: str | None
    reason: str | None
    anchor: str | None
    unscored_reason: str | None

    @property
    def scored(self) -> bool:
        return self.score is not None


@dataclass(frozen=True)
class ResolvedGate:
    """Un filtro ya resuelto."""

    name: str
    status: vocab.GateStatus
    citation: str | None
    reason: str


@dataclass(frozen=True)
class Computed:
    """Lo que sale de la aritmética. Nada de esto lo dice el modelo."""

    value_score: Decimal | None
    coverage: Decimal
    portfolio_bucket: data_vocab.PortfolioBucket | None
    # Por qué no hay cubo, cuando no hay. Se enseña en pantalla: un hueco
    # con su motivo hace que se arregle el YAML; un cubo inventado, no.
    portfolio_note: str | None
    effort_tier: data_vocab.EffortTier
    unscored: tuple[str, ...]


def coverage_of(
    model: ScoringModel, dimensions: tuple[ScoredDimension, ...]
) -> Decimal:
    """Fracción del peso total que sí se pudo puntuar.

    Se calcula sobre el peso **total** del modelo de scoring y no sobre el
    de las dimensiones que el modelo devolvió: una dimensión que nadie
    contestó cuenta como peso perdido, que es justamente lo que la cobertura
    tiene que decir.
    """
    total = Decimal(model.total_weight)
    if total <= 0:  # pragma: no cover - el cargador ya lo impide
        return Decimal(0)
    scored = Decimal(sum(d.weight for d in dimensions if d.scored))
    return (scored / total).quantize(_COVERAGE_PLACES, rounding=ROUND_HALF_UP)


def value_score_of(dimensions: tuple[ScoredDimension, ...]) -> Decimal | None:
    """Media ponderada de las dimensiones puntuadas, renormalizada.

    La renormalización es la regla `missing_data.rule: renormalize`: los
    pesos de las dimensiones sin datos se reparten proporcionalmente entre
    las que sí los tienen, lo que en la práctica es dividir por la suma de
    los pesos puntuados en vez de por el total. Sin eso, una oferta sin
    salario publicado tendría un techo artificial y no sería comparable con
    una que sí lo publica.
    """
    scored = [d for d in dimensions if d.score is not None]
    weight = sum(d.weight for d in scored)
    if not scored or weight <= 0:
        return None
    total = sum(Decimal(d.score or 0) * Decimal(d.weight) for d in scored)
    return (total / Decimal(weight)).quantize(_VALUE_PLACES, rounding=ROUND_HALF_UP)


def _portfolio_bucket(
    value: Decimal | None,
    band: data_vocab.ProbabilityBand,
    *,
    role_family: str | None,
    core_role_families: frozenset[str],
) -> tuple[data_vocab.PortfolioBucket | None, str | None]:
    """El cubo de cartera, o ninguno con su motivo.

    El orden —`discard`, `experimental`, y al final el reparto por banda— lo
    **confirma** `portfolio_assignment.note` desde el 2026-09-05. Hasta
    entonces era una interpretación de este código, porque el YAML no
    declaraba orden y sus reglas se solapan: una oferta de familia fuera del
    objetivo con valor 2,0 encaja a la vez en `discard` y en `experimental`.
    Los motivos que fijó la configuración son que `discard` es un suelo
    absoluto e independiente de los demás ejes, y que estar fuera de
    `objectives.role_families.core` es una vía distinta —exploración— y no
    una posición más del embudo principal.

    `very_low` va a `aspirational` junto con `low`, también desde el
    2026-09-05. No puede tener cubo propio: los cinco nombres de
    `PortfolioBucket` son vocabulario de código y el cargador prohíbe
    ampliarlos.

    Queda un solo hueco, y es el honesto: sin puntuación no hay valor con el
    que decidir nada, así que no hay cubo y se dice por qué.

    Una familia de puesto ausente en la extracción tampoco es «fuera del
    objetivo»: es «no consta», así que no dispara `experimental` y se sigue
    al reparto por banda.
    """
    if value is None:
        return None, (
            "sin puntuación no hay valor con el que asignar cubo: la cobertura "
            "quedó por debajo del mínimo del modelo de scoring"
        )
    if value < VALUE_FLOOR:
        return data_vocab.PortfolioBucket.DISCARD, None
    if role_family is not None and role_family not in core_role_families:
        return data_vocab.PortfolioBucket.EXPERIMENTAL, None

    # Índice directo y no `.get`: el reparto cubre las cuatro bandas desde
    # que `very_low` tiene cubo, y `tests/test_scoring.py` comprueba que no
    # se queda ninguna fuera. Un `.get` con rama de reserva volvería a dejar
    # sitio a un hueco silencioso.
    return BUCKET_OF_BAND[band], None


def _effort_tier(
    model: ScoringModel,
    value: Decimal | None,
    gates: tuple[ResolvedGate, ...],
    band: data_vocab.ProbabilityBand,
) -> data_vocab.EffortTier:
    """El nivel de esfuerzo, en el orden que declara el YAML.

    El orden lo manda `output.effort_tier.evaluation_order` y este código lo
    respeta tal cual, sin reordenarlo por lo que parezca más razonable.

    **Historia de la condición de `cheap`, porque explica por qué es rara.**
    Tal como estaba escrita hasta el 2026-09-05 —«valor >= 3.0 con filtros
    en pending o probabilidad very_low», sin tope superior— y evaluándose
    antes que `full`, ganaba siempre que hubiera un filtro pendiente. Y
    pendiente es el caso habitual: el propio YAML dice de
    `acceptable_conditions` que esas condiciones «rara vez se publican», y en
    la primera puntuación real salió pendiente. El efecto es que `full`
    —adaptar la variante, escribir al recruiter, investigar la empresa— casi
    nunca llegaba a activarse.

    Reordenar no lo arreglaba: poner `full` delante le habría dado `full` a
    una oferta `very_low` excelente, y la configuración dice que `very_low`
    debe ser `cheap`. Así que lo que se estrechó fue la condición: el hueco
    de «filtros en pending» queda acotado a valor entre 3,0 y 4,0, y solo
    `very_low` sigue sin tope de valor.
    """
    any_fail = any(gate.status is vocab.GateStatus.FAIL for gate in gates)
    any_pending = any(gate.status is vocab.GateStatus.PENDING for gate in gates)

    def matches(tier: str) -> bool:
        if tier == data_vocab.EffortTier.SKIP:
            return any_fail or value is None or value < VALUE_FLOOR
        if tier == data_vocab.EffortTier.CHEAP:
            # El hueco de «filtros en pending» queda acotado por arriba a
            # 4,0 desde el 2026-09-05; `very_low` sigue sin tope, porque
            # tiene que ser `cheap` aunque el valor sea alto. Ver el
            # docstring: sin ese tope, `full` casi nunca se activaba.
            return (
                value is not None
                and value >= VALUE_FLOOR
                and (
                    (any_pending and value < VALUE_FULL_EFFORT)
                    or band is data_vocab.ProbabilityBand.VERY_LOW
                )
            )
        if tier == data_vocab.EffortTier.FULL:
            return value is not None and value >= VALUE_FULL_EFFORT and not any_fail
        if tier == data_vocab.EffortTier.STANDARD:
            return (
                value is not None
                and VALUE_FLOOR <= value < VALUE_FULL_EFFORT
                and not any_fail
            )
        return False  # pragma: no cover - el cargador ya lo impide

    for tier in model.effort_evaluation_order:
        if matches(tier):
            return data_vocab.EffortTier(tier)

    # No debería pasar: `skip` cubre todo lo que queda por debajo del suelo
    # y `full`/`standard` cubren lo de arriba. Si pasa, no enviar es lo
    # conservador, y el log dice que hay que mirar el YAML.
    logger.warning(  # pragma: no cover - inalcanzable con el YAML validado
        "ningún nivel de esfuerzo encaja (valor=%s, banda=%s); se aplica skip",
        value,
        band.value,
    )
    return data_vocab.EffortTier.SKIP  # pragma: no cover


def compute(
    model: ScoringModel,
    *,
    dimensions: tuple[ScoredDimension, ...],
    gates: tuple[ResolvedGate, ...],
    band: data_vocab.ProbabilityBand,
    role_family: str | None,
    core_role_families: frozenset[str],
) -> Computed:
    """Todo lo que el código calcula, de una vez.

    El orden de las comparaciones importa en un punto que no se ve: la
    cobertura se **redondea antes** de compararla con el mínimo, no después.
    Así el número que decide es el mismo que sale por la API y se pinta en
    pantalla, y no puede pasar que la pantalla diga 0,500 y el sistema haya
    decidido que no llegaba al mínimo.
    """
    coverage = coverage_of(model, dimensions)
    value = value_score_of(dimensions)
    if coverage < model.minimum_coverage:
        # `missing_data.below_minimum`: no se emite puntuación. Las notas de
        # las dimensiones sí se guardan —son juicios del modelo, y son lo
        # que hace repuntuable la capa— pero no se publica una media que el
        # propio modelo de scoring considera que no sostiene nada.
        value = None

    bucket, note = _portfolio_bucket(
        value,
        band,
        role_family=role_family,
        core_role_families=core_role_families,
    )
    return Computed(
        value_score=value,
        coverage=coverage,
        portfolio_bucket=bucket,
        portfolio_note=note,
        effort_tier=_effort_tier(model, value, gates, band),
        unscored=tuple(d.name for d in dimensions if not d.scored),
    )
