"""La aritmética de la capa `assessment`.

Estos tests son la mitad «el código calcula» del principio de M2. No
aparece ningún modelo: entran notas y estados de filtro, y sale la media
ponderada, la cobertura, el cubo y el esfuerzo.

Todo corre contra el modelo de scoring **sintético**, que pesa 40/30/20/10 y
exige una cobertura mínima de 0,60. Los números de los `assert` están
calculados a mano en el comentario de cada test: si alguien cambia la
fórmula, tiene que discutir con la cuenta y no con un número mágico.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from futuro_api import data_repo
from futuro_api.assessment import scoring
from futuro_api.assessment import vocabularies as vocab
from futuro_api.assessment.scoring import ResolvedGate, ScoredDimension
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.data_repo.models import Dimension, ScoringModel
from tests.conftest import DATA_REPO

MODEL = data_repo.load(DATA_REPO).scoring
CORE = data_repo.load(DATA_REPO).core_role_families

Band = data_vocab.ProbabilityBand
Bucket = data_vocab.PortfolioBucket
Tier = data_vocab.EffortTier


def dimensions(**scores: int | None) -> tuple[ScoredDimension, ...]:
    """Las cuatro dimensiones del modelo sintético, con las notas dadas.

    Lo que no se nombre queda sin puntuar, que es el caso normal y no la
    excepción: en Europa casi ninguna oferta publica salario.
    """
    return tuple(
        ScoredDimension(
            name=dimension.name,
            weight=dimension.weight,
            score=scores.get(dimension.name),
            citation="cita" if scores.get(dimension.name) is not None else None,
            reason="motivo",
            anchor=None,
            unscored_reason=(
                None if scores.get(dimension.name) is not None else "sin datos"
            ),
        )
        for dimension in MODEL.dimensions
    )


def gates(*statuses: vocab.GateStatus) -> tuple[ResolvedGate, ...]:
    return tuple(
        ResolvedGate(
            name=gate.name,
            status=status,
            citation="cita" if status is not vocab.GateStatus.PENDING else None,
            reason="motivo",
        )
        for gate, status in zip(MODEL.gates, statuses, strict=True)
    )


ALL_PASS = gates(*[vocab.GateStatus.PASS] * len(MODEL.gates))


def compute(
    scored: tuple[ScoredDimension, ...],
    *,
    resolved: tuple[ResolvedGate, ...] = ALL_PASS,
    band: Band = Band.HIGH,
    role_family: str | None = "data_engineer",
) -> scoring.Computed:
    return scoring.compute(
        MODEL,
        dimensions=scored,
        gates=resolved,
        band=band,
        role_family=role_family,
        core_role_families=CORE,
    )


# ---------------------------------------------------------------------------
# Media ponderada y renormalización
# ---------------------------------------------------------------------------


def test_the_weighted_average_uses_the_weights_of_the_scoring_model() -> None:
    """(5·40 + 3·30 + 1·20 + 0·10) / 100 = 310/100 = 3,10."""
    result = compute(
        dimensions(ahorro_estimado=5, aprendizaje=3, ubicacion=1, encaje_de_rol=0)
    )
    assert result.value_score == Decimal("3.10")
    assert result.coverage == Decimal("1.000")
    assert result.unscored == ()


def test_missing_dimensions_renormalise_instead_of_capping() -> None:
    """(5·40 + 3·30) / 70 = 290/70 = 4,142857… → 4,14.

    Sin renormalizar, dividir por 100 daría 2,90 y una oferta sin salario
    publicado tendría un techo artificial que la haría incomparable con una
    que sí lo publica. Es la regla `missing_data.rule: renormalize`.
    """
    result = compute(dimensions(ahorro_estimado=5, aprendizaje=3))
    assert result.value_score == Decimal("4.14")
    assert result.coverage == Decimal("0.700")
    assert result.unscored == ("ubicacion", "encaje_de_rol")


def test_coverage_is_measured_against_the_total_weight() -> None:
    """20/100 = 0,200: una dimensión que nadie contestó es peso perdido.

    Si la cobertura se midiera sobre lo que el modelo devolvió, contestar
    menos subiría la cobertura, que es exactamente lo contrario de lo que
    tiene que decir.
    """
    assert compute(dimensions(ubicacion=1)).coverage == Decimal("0.200")


def test_below_the_minimum_coverage_no_score_is_issued() -> None:
    """0,200 < 0,60: `missing_data.below_minimum` dice que no se emite.

    Las notas sí se guardan —son juicios del modelo y son lo que hace
    repuntuable la capa— pero no se publica una media que el propio modelo
    de scoring considera que no sostiene nada. Y un cero no es «no se sabe».
    """
    result = compute(dimensions(ubicacion=5))
    assert result.value_score is None
    assert result.effort_tier is Tier.SKIP


def test_exactly_the_minimum_coverage_does_issue_a_score() -> None:
    """30 + 20 + 10 = 60 sobre 100 = 0,600, que es el mínimo exacto.

    `below_minimum` es «por debajo», no «por debajo o igual».
    """
    result = compute(dimensions(aprendizaje=4, ubicacion=3, encaje_de_rol=3))
    assert result.coverage == Decimal("0.600")
    assert result.value_score is not None


def test_coverage_is_rounded_before_being_compared_to_the_minimum() -> None:
    """El número que decide es el mismo que se pinta.

    Con pesos que no dividen redondo, 3/7 = 0,428571… y se guarda 0,429. Si
    se comparara el valor sin redondear y se guardara el redondeado, la
    pantalla podría decir 0,600 sobre un mínimo de 0,60 y el sistema haber
    decidido que no llegaba.
    """
    model = ScoringModel(
        version="test",
        updated_at="",
        sha256="0" * 64,
        baseline_name="baseline_test",
        baseline={},
        dimensions=(
            Dimension(name="a", weight=3, anchors={0: "x"}, notes={}),
            Dimension(name="b", weight=3, anchors={0: "x"}, notes={}),
            Dimension(name="c", weight=1, anchors={0: "x"}, notes={}),
        ),
        score_min=0,
        score_max=5,
        gates=(),
        probability_bands={},
        portfolio_buckets={},
        effort_tiers={},
        effort_evaluation_order=("skip", "cheap", "full", "standard"),
        minimum_coverage=Decimal("0.42"),
        never_rule="",
    )
    scored = (
        ScoredDimension("a", 3, 4, "cita", "motivo", None, None),
        ScoredDimension("b", 3, None, None, None, None, "sin datos"),
        ScoredDimension("c", 1, None, None, None, None, "sin datos"),
    )
    assert scoring.coverage_of(model, scored) == Decimal("0.429")
    computed = scoring.compute(
        model,
        dimensions=scored,
        gates=(),
        band=Band.HIGH,
        role_family=None,
        core_role_families=frozenset(),
    )
    # 0,429 >= 0,42, así que sí se emite puntuación.
    assert computed.value_score == Decimal("4.00")


def test_nothing_scored_leaves_no_value_and_no_bucket() -> None:
    result = compute(dimensions())
    assert result.coverage == Decimal("0.000")
    assert result.value_score is None
    assert result.portfolio_bucket is None
    assert "cobertura" in (result.portfolio_note or "")


# ---------------------------------------------------------------------------
# Cubos de cartera
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("band", "expected"),
    [
        (Band.HIGH, Bucket.REALISTIC),
        (Band.MEDIUM, Bucket.REALISTIC_STRETCH),
        (Band.LOW, Bucket.ASPIRATIONAL),
    ],
)
def test_the_bucket_comes_from_the_probability_band(
    band: Band, expected: Bucket
) -> None:
    result = compute(
        dimensions(ahorro_estimado=4, aprendizaje=4, ubicacion=4, encaje_de_rol=4),
        band=band,
    )
    assert result.value_score == Decimal("4.00")
    assert result.portfolio_bucket is expected


def test_value_below_the_floor_is_discarded_whatever_the_probability() -> None:
    """`discard: valor < 3.0, con independencia de la probabilidad`.

    Se evalúa **antes** que `experimental`, que es la interpretación que
    este código pone donde el YAML no declara orden: sus reglas se solapan
    —una oferta de familia fuera del objetivo con valor 2,0 encaja en las
    dos— y el YAML solo dice de `discard` que no depende de la probabilidad.
    """
    result = compute(
        dimensions(ahorro_estimado=2, aprendizaje=2, ubicacion=2, encaje_de_rol=2),
        band=Band.HIGH,
        role_family="quantitative_roles",
    )
    assert result.value_score == Decimal("2.00")
    assert result.portfolio_bucket is Bucket.DISCARD


def test_a_family_outside_the_objective_is_experimental() -> None:
    result = compute(
        dimensions(ahorro_estimado=4, aprendizaje=4, ubicacion=4, encaje_de_rol=4),
        role_family="quantitative_roles",
    )
    assert result.portfolio_bucket is Bucket.EXPERIMENTAL


def test_a_family_that_is_absent_is_not_the_same_as_one_outside() -> None:
    """«No consta» no es «fuera del objetivo».

    Si la extracción no pudo determinar la familia, tratarla como
    experimental sería concluir algo que nadie ha dicho. Se sigue al reparto
    por banda.
    """
    result = compute(
        dimensions(ahorro_estimado=4, aprendizaje=4, ubicacion=4, encaje_de_rol=4),
        band=Band.MEDIUM,
        role_family=None,
    )
    assert result.portfolio_bucket is Bucket.REALISTIC_STRETCH


def test_very_low_shares_the_aspirational_bucket_with_low() -> None:
    """El hueco que el NULL en pantalla consiguió que se arreglara.

    Hasta el 2026-09-05 `portfolio_assignment` repartía `high`, `medium` y
    `low` y dejaba `very_low` sin cubo, aunque `effort_tier` sí la
    contempla. El código no se lo inventó: dejaba el cubo vacío con el
    motivo escrito debajo, y eso es lo que hizo que se decidiera. No puede
    tener cubo propio —los cinco nombres son vocabulario de código— así que
    va con `low`.
    """
    result = compute(
        dimensions(ahorro_estimado=4, aprendizaje=4, ubicacion=4, encaje_de_rol=4),
        band=Band.VERY_LOW,
    )
    assert result.portfolio_bucket is Bucket.ASPIRATIONAL
    assert result.portfolio_note is None


def test_every_probability_band_has_a_bucket() -> None:
    """Ninguna banda se queda fuera del reparto.

    Es lo que permite que `_portfolio_bucket` indexe la tabla directamente
    en vez de usar `.get` con una rama de reserva: sin este test, añadir una
    banda al vocabulario dejaría un hueco silencioso o un `KeyError` en
    producción.
    """
    assert set(scoring.BUCKET_OF_BAND) == set(Band)


# ---------------------------------------------------------------------------
# Nivel de esfuerzo
# ---------------------------------------------------------------------------


def test_a_failed_gate_skips_whatever_the_value() -> None:
    result = compute(
        dimensions(ahorro_estimado=5, aprendizaje=5, ubicacion=5, encaje_de_rol=5),
        resolved=gates(
            vocab.GateStatus.FAIL, vocab.GateStatus.PASS, vocab.GateStatus.PASS
        ),
    )
    assert result.value_score == Decimal("5.00")
    assert result.effort_tier is Tier.SKIP


def test_a_high_value_with_everything_decided_is_full_effort() -> None:
    result = compute(
        dimensions(ahorro_estimado=5, aprendizaje=4, ubicacion=4, encaje_de_rol=4)
    )
    assert result.value_score == Decimal("4.40")
    assert result.effort_tier is Tier.FULL


def test_a_middling_value_with_everything_decided_is_standard_effort() -> None:
    result = compute(
        dimensions(ahorro_estimado=3, aprendizaje=4, ubicacion=3, encaje_de_rol=3)
    )
    assert result.value_score == Decimal("3.30")
    assert result.effort_tier is Tier.STANDARD


def test_a_pending_gate_no_longer_steals_full_effort_from_a_good_offer() -> None:
    """El arreglo del 2026-09-05, y el porqué.

    Con la condición anterior de `cheap` —«valor >= 3.0 con filtros en
    pending», sin tope— y evaluándose antes que `full`, una oferta de 4,40
    con un filtro pendiente salía `cheap`. Y pendiente es el caso habitual:
    el propio modelo de scoring dice que esas condiciones «rara vez se
    publican», y en la primera puntuación real salió pendiente. El efecto
    era que `full` casi nunca se activaba.
    """
    result = compute(
        dimensions(ahorro_estimado=5, aprendizaje=4, ubicacion=4, encaje_de_rol=4),
        resolved=gates(
            vocab.GateStatus.PASS, vocab.GateStatus.PENDING, vocab.GateStatus.PASS
        ),
    )
    assert result.value_score == Decimal("4.40")
    assert result.effort_tier is Tier.FULL


def test_a_pending_gate_still_makes_a_middling_offer_cheap() -> None:
    """El hueco de `cheap` sigue existiendo, acotado entre 3,0 y 4,0.

    Estrecharlo no era quitarlo: una oferta que solo llega al aprobado y
    encima tiene condiciones sin comprobar es justamente donde «solo si
    postularse es barato» significa algo.
    """
    result = compute(
        dimensions(ahorro_estimado=3, aprendizaje=4, ubicacion=3, encaje_de_rol=3),
        resolved=gates(
            vocab.GateStatus.PASS, vocab.GateStatus.PENDING, vocab.GateStatus.PASS
        ),
    )
    assert result.value_score == Decimal("3.30")
    assert result.effort_tier is Tier.CHEAP


def test_a_very_low_probability_is_cheap_effort_even_with_a_good_value() -> None:
    """`very_low` sí sigue sin tope de valor, y es deliberado.

    Es la asimetría que hizo que reordenar no sirviera: poner `full` delante
    de `cheap` le habría dado `full` a esta oferta, y el modelo de scoring
    dice que `very_low` se registra «por aprendizaje, no por expectativa».
    """
    result = compute(
        dimensions(ahorro_estimado=5, aprendizaje=4, ubicacion=4, encaje_de_rol=4),
        band=Band.VERY_LOW,
    )
    assert result.value_score == Decimal("4.40")
    assert result.effort_tier is Tier.CHEAP


def test_the_evaluation_order_of_the_yaml_is_the_one_that_is_applied() -> None:
    """Prueba directa de que el orden sale del YAML y no de este código.

    Con `[standard, cheap, skip, full]`, la misma oferta con un filtro
    pendiente sale `standard` en vez de `cheap`, porque ahora `standard` se
    evalúa antes. Si el orden estuviera escrito en Python, este test no
    podría existir.
    """
    reordered = ScoringModel(
        **{
            **MODEL.__dict__,
            "effort_evaluation_order": ("standard", "cheap", "skip", "full"),
        }
    )
    result = scoring.compute(
        reordered,
        dimensions=dimensions(
            ahorro_estimado=3, aprendizaje=4, ubicacion=3, encaje_de_rol=3
        ),
        gates=gates(
            vocab.GateStatus.PASS, vocab.GateStatus.PENDING, vocab.GateStatus.PASS
        ),
        band=Band.HIGH,
        role_family="data_engineer",
        core_role_families=CORE,
    )
    assert result.effort_tier is Tier.STANDARD
