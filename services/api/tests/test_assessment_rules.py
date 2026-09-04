"""Lo que el código le corrige al modelo al puntuar.

Cada test cambia **una** cosa sobre una respuesta que pasaría entera, y
comprueba qué clase de respuesta le da el código. Las tres clases son las
mismas que en la extracción de M1, y la del medio es la que manda el
contrato:

1. rechazo, cuando no hay degradación honesta;
2. sin puntuar, cuando la nota no se sostiene —no se corrige la nota, se
   quita—;
3. degradación al máximo que el contrato permite.

Todo contra el repositorio de datos y el anuncio **sintéticos**.
"""

from __future__ import annotations

import pytest

from futuro_api import data_repo
from futuro_api.assessment import rules
from futuro_api.assessment import vocabularies as vocab
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.offers import vocabularies as offers_vocab
from tests import synthetic
from tests.conftest import DATA_REPO

REPO = data_repo.load(DATA_REPO)
POSITIONS = (0, 1, 2)


def validate(draft: object, positions: tuple[int, ...] = POSITIONS):  # type: ignore[no-untyped-def]
    return rules.validate_scoring(
        draft,  # type: ignore[arg-type]
        repo=REPO,
        raw_text=synthetic.ADVERT,
        requirement_positions=positions,
    )


def rules_applied(validated: rules.ValidatedScoring) -> list[str]:
    return [correction.rule for correction in validated.corrections]


def dimension(validated: rules.ValidatedScoring, name: str):  # type: ignore[no-untyped-def]
    return next(d for d in validated.dimensions if d.name == name)


def gate(validated: rules.ValidatedScoring, name: str):  # type: ignore[no-untyped-def]
    return next(g for g in validated.gates if g.name == name)


# ---------------------------------------------------------------------------
# El camino que pasa
# ---------------------------------------------------------------------------


def test_a_good_response_passes_without_corrections() -> None:
    validated = validate(synthetic.good_scoring_draft())
    assert validated.corrections == ()
    assert [d.name for d in validated.dimensions] == list(REPO.scoring.dimension_names)
    assert all(d.scored for d in validated.dimensions)
    assert all(g.status is vocab.GateStatus.PASS for g in validated.gates)


def test_the_dimensions_come_back_in_the_order_of_the_scoring_model() -> None:
    """Y no en el que las devolvió el modelo.

    El orden es el de las barras de la pantalla, y el único que significa
    algo es el del YAML.
    """
    reversed_answer = [
        synthetic.dimension_score(name)
        for name in reversed(synthetic.SYNTHETIC_DIMENSIONS)
    ]
    validated = validate(synthetic.good_scoring_draft(dimensions=reversed_answer))
    assert [d.name for d in validated.dimensions] == list(REPO.scoring.dimension_names)


def test_a_scored_dimension_keeps_the_anchor_that_justifies_it() -> None:
    """La nota se guarda con el texto del ancla que la explica.

    Sale del YAML al puntuar y se copia en la fila, así que la pantalla no
    depende del repositorio de datos para explicar una nota vieja.
    """
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("ahorro_estimado", score=3),
            *[
                synthetic.dimension_score(name)
                for name in synthetic.SYNTHETIC_DIMENSIONS[1:]
            ],
        ]
    )
    resolved = dimension(validate(draft), "ahorro_estimado")
    assert resolved.anchor == "Entre 3.000 y 5.000 EUR más al año."


def test_a_dimension_the_model_could_not_score_is_not_a_correction() -> None:
    """Decir «no la puedo puntuar» es la respuesta correcta, no un fallo.

    En Europa casi ninguna oferta publica salario, así que este camino es el
    normal. Contarlo como corrección haría que la cuenta de infracciones del
    modelo midiera sobre todo lo bien que se porta.
    """
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score(
                "ahorro_estimado",
                score=None,
                citation=None,
                reason="el anuncio no publica compensación",
            ),
            *[
                synthetic.dimension_score(name)
                for name in synthetic.SYNTHETIC_DIMENSIONS[1:]
            ],
        ]
    )
    validated = validate(draft)
    resolved = dimension(validated, "ahorro_estimado")
    assert not resolved.scored
    assert resolved.unscored_reason == "el anuncio no publica compensación"
    assert validated.corrections == ()


# ---------------------------------------------------------------------------
# Una nota sin cita no entra
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("citation", "label"),
    [
        (None, "sin cita ninguna"),
        ("", "con la cita vacía"),
        ("SQ", "con una cita más corta que tres caracteres"),
        (synthetic.INVENTED_QUOTE, "con una cita que no está en el anuncio"),
    ],
)
def test_a_score_without_a_usable_citation_leaves_the_dimension_unscored(
    citation: str | None, label: str
) -> None:
    """La regla central del contrato, en sus cuatro formas.

    No se corrige la nota ni se recorta: se quita. Una nota sin cita
    comprobable no es una nota más baja, es una nota que no existe.
    """
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("ahorro_estimado", score=5, citation=citation),
            *[
                synthetic.dimension_score(name)
                for name in synthetic.SYNTHETIC_DIMENSIONS[1:]
            ],
        ]
    )
    validated = validate(draft)
    resolved = dimension(validated, "ahorro_estimado")
    assert not resolved.scored, label
    assert resolved.score is None
    assert "score_without_citation" in rules_applied(validated)


def test_a_citation_survives_the_noise_of_copying() -> None:
    """Comillas curvas, espacios y mayúsculas se perdonan; el resto no.

    Es la misma normalización que usa la extracción, y a propósito: «una
    cita se comprueba contra el anuncio» tiene que significar exactamente lo
    mismo en las dos capas.
    """
    noisy = "  imprescindible   SQL\n avanzado  "
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("ahorro_estimado", score=4, citation=noisy),
            *[
                synthetic.dimension_score(name)
                for name in synthetic.SYNTHETIC_DIMENSIONS[1:]
            ],
        ]
    )
    assert dimension(validate(draft), "ahorro_estimado").score == 4


def test_a_score_out_of_scale_is_dropped_and_not_clamped() -> None:
    """Recortar un 9 a un 5 sería inventarse una nota.

    El modelo dijo algo que no significa nada en esta escala; lo honesto es
    que la dimensión quede sin puntuar y que quede registrado.
    """
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("ahorro_estimado", score=9),
            *[
                synthetic.dimension_score(name)
                for name in synthetic.SYNTHETIC_DIMENSIONS[1:]
            ],
        ]
    )
    validated = validate(draft)
    assert not dimension(validated, "ahorro_estimado").scored
    assert "score_out_of_scale" in rules_applied(validated)


def test_a_dimension_the_model_did_not_answer_is_unscored_and_counted() -> None:
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score(name)
            for name in synthetic.SYNTHETIC_DIMENSIONS[:2]
        ]
    )
    validated = validate(draft)
    assert not dimension(validated, "ubicacion").scored
    assert rules_applied(validated).count("missing_dimension") == 2


def test_a_dimension_the_scoring_model_does_not_have_is_discarded() -> None:
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("prestigio_inventado"),
            *[
                synthetic.dimension_score(name)
                for name in synthetic.SYNTHETIC_DIMENSIONS
            ],
        ]
    )
    validated = validate(draft)
    assert [d.name for d in validated.dimensions] == list(REPO.scoring.dimension_names)
    assert "unknown_dimension" in rules_applied(validated)


# ---------------------------------------------------------------------------
# Los filtros nunca se suponen superados, y tampoco incumplidos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [vocab.GateStatus.PASS, vocab.GateStatus.FAIL, vocab.GateStatus.STRETCH],
)
def test_a_decided_gate_without_a_citation_becomes_pending(
    status: vocab.GateStatus,
) -> None:
    """Y `pending`, nunca `fail`: «no consta» no es «incumple».

    Es la regla del YAML —«un filtro que no puede evaluarse queda pending,
    nunca se supone superado»— y su simétrica, que no está escrita pero se
    deduce: tampoco se supone incumplido.
    """
    draft = synthetic.good_scoring_draft(
        gates=[
            synthetic.gate_verdict(
                "permiso_de_trabajo",
                status=status,
                citation=synthetic.INVENTED_QUOTE,
            ),
            *[synthetic.gate_verdict(name) for name in synthetic.SYNTHETIC_GATES[1:]],
        ]
    )
    validated = validate(draft)
    resolved = gate(validated, "permiso_de_trabajo")
    assert resolved.status is vocab.GateStatus.PENDING
    assert resolved.citation is None
    assert "verdict_without_citation" in rules_applied(validated)


def test_a_pending_gate_does_not_keep_a_citation() -> None:
    """Si algo del anuncio lo resolviera, no estaría pendiente."""
    draft = synthetic.good_scoring_draft(
        gates=[
            synthetic.gate_verdict(
                "permiso_de_trabajo",
                status=vocab.GateStatus.PENDING,
                citation=synthetic.QUOTE,
            ),
            *[synthetic.gate_verdict(name) for name in synthetic.SYNTHETIC_GATES[1:]],
        ]
    )
    assert gate(validate(draft), "permiso_de_trabajo").citation is None


def test_a_gate_the_model_did_not_evaluate_is_pending_and_counted() -> None:
    draft = synthetic.good_scoring_draft(
        gates=[synthetic.gate_verdict(synthetic.SYNTHETIC_GATES[0])]
    )
    validated = validate(draft)
    assert gate(validated, "suelo_de_ahorro").status is vocab.GateStatus.PENDING
    assert rules_applied(validated).count("missing_gate") == 2


def test_a_gate_the_scoring_model_does_not_have_is_discarded() -> None:
    draft = synthetic.good_scoring_draft(
        gates=[
            synthetic.gate_verdict("filtro_inventado"),
            *[synthetic.gate_verdict(name) for name in synthetic.SYNTHETIC_GATES],
        ]
    )
    validated = validate(draft)
    assert [g.name for g in validated.gates] == list(REPO.scoring.gate_names)
    assert "unknown_gate" in rules_applied(validated)


def test_a_gate_without_a_reason_still_says_something_readable() -> None:
    """La columna es obligatoria y un motivo en blanco parece un fallo nuestro.

    Así se ve que el hueco lo dejó el modelo, y queda contado.
    """
    draft = synthetic.good_scoring_draft(
        gates=[
            synthetic.gate_verdict("permiso_de_trabajo", reason="   "),
            *[synthetic.gate_verdict(name) for name in synthetic.SYNTHETIC_GATES[1:]],
        ]
    )
    assert gate(validate(draft), "permiso_de_trabajo").reason == rules.NO_REASON


# ---------------------------------------------------------------------------
# El cruce de requisitos: `evidence_ref` tiene que resolver
# ---------------------------------------------------------------------------


def test_meets_with_a_usable_evidence_holds() -> None:
    draft = synthetic.good_scoring_draft(
        requirements=[
            synthetic.requirement_cross(
                0,
                match=offers_vocab.RequirementMatch.MEETS,
                evidence_ref=synthetic.USABLE_BULLET,
            )
        ]
    )
    validated = validate(draft)
    match = validated.requirement_matches[0]
    assert match.match is offers_vocab.RequirementMatch.MEETS
    assert match.evidence_ref == synthetic.USABLE_BULLET
    assert validated.corrections == ()


def test_meets_without_an_evidence_ref_degrades_to_partial() -> None:
    """La regla de M1, ahora llamada con datos de verdad.

    `enforce_match_rule` se escribió y se probó en M1 sin poder usarse,
    porque el esquema del modelo no tenía `match`. Aquí sí lo tiene.
    """
    draft = synthetic.good_scoring_draft(
        requirements=[
            synthetic.requirement_cross(
                0, match=offers_vocab.RequirementMatch.MEETS, evidence_ref=None
            )
        ]
    )
    validated = validate(draft)
    assert (
        validated.requirement_matches[0].match is offers_vocab.RequirementMatch.PARTIAL
    )
    assert "meets_needs_evidence_ref" in rules_applied(validated)


def test_meets_with_an_evidence_ref_that_does_not_exist_degrades() -> None:
    """Una referencia que no resuelve es el parecido de palabras del contrato.

    Con la forma de un identificador, que es peor: parece comprobable y no
    lo es. En M1 solo se podía exigir presencia; aquí se exige que exista.
    """
    draft = synthetic.good_scoring_draft(
        requirements=[
            synthetic.requirement_cross(
                0,
                match=offers_vocab.RequirementMatch.MEETS,
                evidence_ref="evidencia_que_no_existe",
            )
        ]
    )
    validated = validate(draft)
    match = validated.requirement_matches[0]
    assert match.match is offers_vocab.RequirementMatch.PARTIAL
    assert match.evidence_ref is None
    assert "evidence_ref_does_not_resolve" in rules_applied(validated)


def test_meets_on_an_evidence_that_is_not_usable_degrades() -> None:
    """Existe, pero no está comprobada o no es divulgable.

    Los dos estados, no uno: `verified` dice que el contenido está
    comprobado y `cv_usage` que se puede divulgar. Un bullet `candidate` no
    sostiene una afirmación de cumplimiento.
    """
    draft = synthetic.good_scoring_draft(
        requirements=[
            synthetic.requirement_cross(
                0,
                match=offers_vocab.RequirementMatch.MEETS,
                evidence_ref=synthetic.UNUSABLE_BULLET,
            )
        ]
    )
    validated = validate(draft)
    match = validated.requirement_matches[0]
    assert match.match is offers_vocab.RequirementMatch.PARTIAL
    assert match.evidence_ref is None
    assert "evidence_ref_not_usable" in rules_applied(validated)


def test_a_cross_pointing_at_a_requirement_that_does_not_exist_is_discarded() -> None:
    draft = synthetic.good_scoring_draft(requirements=[synthetic.requirement_cross(99)])
    validated = validate(draft)
    assert validated.requirement_matches == ()
    assert "requirement_out_of_range" in rules_applied(validated)


def test_a_requirement_crossed_twice_keeps_the_first() -> None:
    draft = synthetic.good_scoring_draft(
        requirements=[
            synthetic.requirement_cross(0, match=offers_vocab.RequirementMatch.PARTIAL),
            synthetic.requirement_cross(
                0, match=offers_vocab.RequirementMatch.NO_EVIDENCE
            ),
        ]
    )
    validated = validate(draft)
    assert len(validated.requirement_matches) == 1
    assert (
        validated.requirement_matches[0].match is offers_vocab.RequirementMatch.PARTIAL
    )
    assert "duplicated_requirement_cross" in rules_applied(validated)


# ---------------------------------------------------------------------------
# Rechazo: cuando no hay degradación honesta
# ---------------------------------------------------------------------------


def test_a_band_without_a_reason_is_rejected() -> None:
    """No hay degradación posible: la columna es obligatoria.

    Y al contrario que una nota, una banda no se puede dejar «sin puntuar»:
    un juicio sin motivo no se puede enseñar ni discutir.
    """
    with pytest.raises(rules.AssessmentRejected, match="sin motivo"):
        validate(synthetic.good_scoring_draft(probability_reason="   "))


def test_a_response_about_other_dimensions_entirely_is_rejected() -> None:
    """Cero coincidencias es una respuesta a otra pregunta.

    Guardarla daría cobertura cero y una fila que no significa nada. Con
    una lista vacía, en cambio, se aceptan cuatro dimensiones sin puntuar:
    eso sí es una respuesta, aunque no diga gran cosa.
    """
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("prestigio"),
            synthetic.dimension_score("aprendizaje_inventado"),
        ]
    )
    with pytest.raises(rules.AssessmentRejected, match="ninguna de las dimensiones"):
        validate(draft)


def test_an_empty_dimension_list_is_accepted_as_all_unscored() -> None:
    validated = validate(synthetic.good_scoring_draft(dimensions=[]))
    assert all(not d.scored for d in validated.dimensions)


def test_the_same_dimension_scored_twice_with_different_marks_is_rejected() -> None:
    """Elegir una sería adivinar cuál quiso decir."""
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("ahorro_estimado", score=1),
            synthetic.dimension_score("ahorro_estimado", score=5),
        ]
    )
    with pytest.raises(rules.AssessmentRejected, match="dos veces"):
        validate(draft)


def test_the_same_dimension_twice_with_the_same_mark_is_only_a_correction() -> None:
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("ahorro_estimado", score=3),
            synthetic.dimension_score("ahorro_estimado", score=3),
        ]
    )
    validated = validate(draft)
    assert "duplicated_dimension" in rules_applied(validated)


def test_all_the_violations_come_out_at_once() -> None:
    """Si hay que cambiar el prompt, conviene verlas juntas.

    Descubrirlas de una en una se paga en reintentos.
    """
    draft = synthetic.good_scoring_draft(
        dimensions=[
            synthetic.dimension_score("prestigio"),
            synthetic.dimension_score("otra_inventada"),
        ],
        probability_reason="",
    )
    with pytest.raises(rules.AssessmentRejected) as raised:
        validate(draft)
    assert len(raised.value.violations) == 2


# ---------------------------------------------------------------------------
# La variante: rechazo y nada más
# ---------------------------------------------------------------------------


def test_a_variant_that_exists_is_accepted() -> None:
    validated = rules.validate_variant(
        synthetic.good_variant_draft(), variants=REPO.variants
    )
    assert validated.variant == "cartografia_nautica"


def test_a_variant_that_does_not_exist_is_rejected() -> None:
    """No hay degradación honesta: elegir otra sería inventar.

    Se prueba con `batimetria_profunda`, que **está declarada** en
    `cv_variants.yaml` y no tiene carpeta. Es el caso realista: el modelo la
    ve mencionada en la guía y la elige.
    """
    with pytest.raises(rules.AssessmentRejected, match="batimetria_profunda"):
        rules.validate_variant(
            synthetic.good_variant_draft(variant="batimetria_profunda"),
            variants=REPO.variants,
        )


def test_a_variant_without_a_reason_is_rejected() -> None:
    """`ARCHITECTURE.md` §7 dice que la app enseña *ese razonamiento*.

    Sin razonamiento no hay nada que enseñar, así que la recomendación no
    sirve para lo que existe.
    """
    with pytest.raises(rules.AssessmentRejected, match="sin motivo"):
        rules.validate_variant(
            synthetic.good_variant_draft(reason=" "), variants=REPO.variants
        )


def test_the_output_schema_cannot_carry_a_value_score() -> None:
    """«El código nunca acepta un `value_score` calculado por el modelo».

    La forma fuerte de esa regla no es tacharlo al validar: es que no exista
    el campo. Con `extra="forbid"`, una respuesta que lo mande **no
    parsea**, así que no hay ningún camino en el que llegue a la base de
    datos. Es el mismo patrón que hizo `active_verified` inalcanzable en M1.
    """
    from pydantic import ValidationError

    from futuro_api.assessment import schemas

    payload = synthetic.good_scoring_draft().model_dump()
    payload["value_score"] = 4.9
    with pytest.raises(ValidationError, match="value_score"):
        schemas.ScoringDraft.model_validate(payload)

    assert "value_score" not in schemas.ScoringDraft.model_fields
    assert "coverage" not in schemas.ScoringDraft.model_fields
    assert "portfolio_bucket" not in schemas.ScoringDraft.model_fields
    assert "effort_tier" not in schemas.ScoringDraft.model_fields
    # Y tampoco el peso: dejar que el modelo lo repita sería darle una
    # segunda oportunidad de cambiarlo.
    assert "weight" not in schemas.DimensionScore.model_fields


def test_the_band_vocabulary_is_the_one_the_scoring_model_declares() -> None:
    """Guarda contra que el enum del código y el YAML se separen."""
    assert set(REPO.scoring.probability_bands) == {
        band.value for band in data_vocab.ProbabilityBand
    }
