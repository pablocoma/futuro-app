"""Lo que el código le corrige al modelo, y lo que no le perdona.

La estructura de cada test es la misma: se parte de `good_draft()`, que
cumple todas las reglas, y se estropea **un solo campo**. Así lo que falla
es siempre inequívoco, y un test que empiece a pasar por el motivo
equivocado se nota.
"""

from __future__ import annotations

import pytest

from futuro_api.offers import rules
from futuro_api.offers import vocabularies as vocab
from tests.synthetic import ADVERT, absent, good_draft, inferred, published


def _rules_applied(result: rules.ValidatedExtraction) -> set[str]:
    return {correction["rule"] or "" for correction in result.corrections}


def _corrections_for(
    result: rules.ValidatedExtraction, field: str
) -> list[dict[str, str | None]]:
    return [c for c in result.corrections if c["field"] == field]


# ---------------------------------------------------------------------------
# La línea base
# ---------------------------------------------------------------------------


def test_a_well_formed_draft_needs_no_corrections() -> None:
    result = rules.validate(good_draft(), ADVERT)
    assert result.corrections == []
    assert len(result.requirements) == 4
    assert len(result.anomalies) == 1
    assert result.evidence["title"] == {
        "status": "published",
        "source_quote": "Ingeniero de Datos",
    }
    assert result.evidence["hiring_regions"] == {"status": "absent"}


def test_an_inferred_field_keeps_its_reasoning_and_confidence() -> None:
    result = rules.validate(good_draft(), ADVERT)
    assert result.evidence["role_family"]["status"] == "inferred"
    assert result.evidence["role_family"]["confidence"] == "high"
    assert result.evidence["role_family"]["reasoning"]
    # La cita no se guarda en un campo inferido: no hay ninguna.
    assert "source_quote" not in result.evidence["role_family"]


# ---------------------------------------------------------------------------
# Citas: la comprobación que el modelo no puede falsear
# ---------------------------------------------------------------------------


def test_a_fabricated_quote_drops_the_field() -> None:
    """Una cita que no está en el anuncio no prueba nada.

    El campo pasa a `absent`, que es lo único honesto que se puede afirmar
    cuando la prueba no aparece. No se rechaza la extracción entera: el
    resto de los campos siguen sostenidos por sus propias citas.
    """
    draft = good_draft()
    draft.identification.location = published(
        "Madrid", "el puesto es en Madrid, en nuestra sede central"
    )
    result = rules.validate(draft, ADVERT)

    assert result.columns["location"] is None
    assert result.evidence["location"] == {"status": "absent"}
    assert _corrections_for(result, "location")[0]["rule"] == "unverified_quote"


def test_typographic_noise_does_not_break_a_real_quote() -> None:
    """Comillas curvas, saltos de línea y mayúsculas no descartan una cita.

    Un modelo reescribe esos detalles al copiar sin estar inventando nada.
    Lo que no se perdona es cambiar las palabras.
    """
    draft = good_draft()
    draft.identification.work_mode = published(
        vocab.WorkMode.HYBRID,
        "  MODALIDAD  HÍBRIDA:\n\tdos días   en oficina  ",
    )
    result = rules.validate(draft, ADVERT)

    assert result.columns["work_mode"] is vocab.WorkMode.HYBRID
    assert result.corrections == []


def test_a_quote_too_short_to_prove_anything_is_rejected() -> None:
    draft = good_draft()
    draft.identification.title = published("Ingeniero de Datos", "de")
    with pytest.raises(rules.ExtractionRejected, match="demasiado corta"):
        rules.validate(draft, ADVERT)


# ---------------------------------------------------------------------------
# El sobre de evidencia
# ---------------------------------------------------------------------------


def test_absent_with_a_value_is_rejected() -> None:
    """Es la forma que toma rellenar un hueco con una estimación de mercado.

    No hay degradación posible: si el dato no aparece en el anuncio, el
    valor no puede venir de ningún sitio legítimo.
    """
    draft = good_draft()
    draft.compensation.equity = absent()
    draft.compensation.equity.value = "0,5% en opciones"
    with pytest.raises(rules.ExtractionRejected, match="absent.*valor rellenado"):
        rules.validate(draft, ADVERT)


def test_published_without_a_quote_is_rejected() -> None:
    draft = good_draft()
    draft.identification.title.evidence.source_quote = None
    with pytest.raises(rules.ExtractionRejected, match="sin cita"):
        rules.validate(draft, ADVERT)


def test_inferred_without_reasoning_is_rejected() -> None:
    draft = good_draft()
    draft.identification.role_family.evidence.reasoning = "   "
    with pytest.raises(rules.ExtractionRejected, match="sin reasoning"):
        rules.validate(draft, ADVERT)


def test_inferred_without_confidence_is_rejected() -> None:
    draft = good_draft()
    draft.identification.role_family.evidence.confidence = None
    with pytest.raises(rules.ExtractionRejected, match="sin confidence"):
        rules.validate(draft, ADVERT)


def test_evidence_without_a_value_is_rejected() -> None:
    """Afirmar que algo consta y no decir qué consta."""
    draft = good_draft()
    draft.identification.title.value = None
    with pytest.raises(rules.ExtractionRejected, match="sin valor"):
        rules.validate(draft, ADVERT)


def test_every_violation_is_reported_together() -> None:
    """Las infracciones se juntan antes de lanzar, no se para en la primera.

    Si hay que cambiar el prompt o el modelo, conviene verlas de una vez en
    lugar de descubrirlas de una en una a base de reintentos que se pagan.
    """
    draft = good_draft()
    draft.identification.title.evidence.source_quote = None
    draft.identification.role_family.evidence.confidence = None
    draft.compensation.equity = absent()
    draft.compensation.equity.value = "algo"

    with pytest.raises(rules.ExtractionRejected) as raised:
        rules.validate(draft, ADVERT)
    assert len(raised.value.violations) == 3


# ---------------------------------------------------------------------------
# Estado del anuncio
# ---------------------------------------------------------------------------


def test_active_verified_is_downgraded_to_unverifiable() -> None:
    """Que el anuncio se declare activo no es una comprobación.

    Y de un texto pegado no hay URL que consultar, así que en M1 el valor
    es inalcanzable por mucho que el modelo lo afirme.
    """
    draft = good_draft()
    draft.identification.posting_status = published(
        vocab.PostingStatus.ACTIVE_VERIFIED, "oferta para cliente"
    )
    result = rules.validate(draft, ADVERT)

    assert result.columns["posting_status"] is vocab.PostingStatus.UNVERIFIABLE
    assert "active_verified_needs_a_check" in _rules_applied(result)


def test_posting_status_absent_becomes_unverifiable_without_a_correction() -> None:
    """`unverifiable` significa literalmente «no se puede verificar».

    Cuando el anuncio no dice nada, eso es la verdad y no una corrección:
    la evidencia sigue registrada como `absent`.
    """
    result = rules.validate(good_draft(), ADVERT)
    assert result.columns["posting_status"] is vocab.PostingStatus.UNVERIFIABLE
    assert result.evidence["posting_status"] == {"status": "absent"}
    assert result.corrections == []


def test_an_expired_advert_keeps_its_status() -> None:
    draft = good_draft()
    draft.identification.posting_status = published(
        vocab.PostingStatus.EXPIRED, "oferta para cliente"
    )
    result = rules.validate(draft, ADVERT)
    assert result.columns["posting_status"] is vocab.PostingStatus.EXPIRED


# ---------------------------------------------------------------------------
# Las dos empresas
# ---------------------------------------------------------------------------


def test_the_two_companies_stay_apart() -> None:
    result = rules.validate(good_draft(), ADVERT)
    assert result.posting_company_name == "Reclutamiento Bahía"
    assert result.employer_company_name == "Astillero Nube S.L."
    assert result.employer_confidence is vocab.EmployerConfidence.HIGH
    assert result.evidence["employer_company_id"]["status"] == "inferred"


def test_an_employer_without_confidence_is_rejected() -> None:
    """Registrarlo sin confianza sería registrar una inferencia como hecho."""
    draft = good_draft()
    draft.companies.employer_confidence = None
    with pytest.raises(rules.ExtractionRejected, match="employer_confidence"):
        rules.validate(draft, ADVERT)


def test_a_self_posted_employer_is_confirmed() -> None:
    """Si quien publica es el propio empleador, no hay nada que inferir."""
    draft = good_draft()
    draft.companies.employer = inferred(
        "reclutamiento bahía", "parece que publica para sí misma"
    )
    result = rules.validate(draft, ADVERT)

    assert result.employer_confidence is vocab.EmployerConfidence.CONFIRMED
    assert "self_posted_employer_is_confirmed" in _rules_applied(result)


def test_a_confidence_without_an_employer_is_dropped() -> None:
    draft = good_draft()
    draft.companies.employer = absent()
    result = rules.validate(draft, ADVERT)

    assert result.employer_company_name is None
    assert result.employer_confidence is None
    assert "confidence_without_an_employer" in _rules_applied(result)


# ---------------------------------------------------------------------------
# Requisitos
# ---------------------------------------------------------------------------


def test_meets_without_an_evidence_ref_becomes_partial() -> None:
    """La prohibición central del contrato, probada directamente.

    En M1 el esquema del modelo no tiene `match`, así que esta regla no se
    dispara con ninguna respuesta real. Se prueba aquí para que M2 la
    herede funcionando en vez de escribirla con prisa.
    """
    match, correction = rules.enforce_match_rule(
        "requirements[0].match", vocab.RequirementMatch.MEETS, None
    )
    assert match is vocab.RequirementMatch.PARTIAL
    assert correction is not None
    assert correction.rule == "meets_needs_evidence_ref"


def test_meets_with_an_evidence_ref_is_kept() -> None:
    match, correction = rules.enforce_match_rule(
        "requirements[0].match", vocab.RequirementMatch.MEETS, "ev-inventada-01"
    )
    assert match is vocab.RequirementMatch.MEETS
    assert correction is None


def test_requirements_have_no_match_in_this_slice() -> None:
    """Cruzar contra el banco de evidencias exige el repositorio privado.

    NULL significa «sin evaluar», que no es lo mismo que `no_evidence`,
    «evaluado y no hay nada». Confundirlos haría que M2 se saltara los
    requisitos que nadie ha mirado todavía.
    """
    result = rules.validate(good_draft(), ADVERT)
    assert all(requirement.match is None for requirement in result.requirements)
    assert all(requirement.evidence_ref is None for requirement in result.requirements)


def test_a_requirement_with_a_fabricated_quote_is_dropped_and_renumbered() -> None:
    """Un requisito cuya cita no está es un requisito que nadie ha pedido.

    Se descarta, y los siguientes se renumeran: la posición tiene que
    quedar contigua porque es el orden del anuncio.
    """
    draft = good_draft()
    draft.requirements[1].source_quote = "Se requiere titulación universitaria"
    result = rules.validate(draft, ADVERT)

    assert [r.position for r in result.requirements] == [1, 2, 3]
    assert [r.text for r in result.requirements] == [
        "SQL avanzado",
        "Python",
        "Cinco años de experiencia con Marea",
    ]
    assert "unverified_quote" in _rules_applied(result)


def test_an_anomaly_follows_its_requirement_after_a_renumbering() -> None:
    """La anomalía apuntaba al índice 3 del modelo, ahora en la posición 3."""
    draft = good_draft()
    draft.requirements[1].source_quote = "Se requiere titulación universitaria"
    result = rules.validate(draft, ADVERT)

    assert result.anomalies[0].requirement_position == 3
    assert result.requirements[2].kind is vocab.RequirementKind.ANOMALOUS


def test_a_requirement_without_text_is_rejected() -> None:
    draft = good_draft()
    draft.requirements[0].text = "  "
    with pytest.raises(rules.ExtractionRejected, match="sin texto"):
        rules.validate(draft, ADVERT)


# ---------------------------------------------------------------------------
# Anomalías
# ---------------------------------------------------------------------------


def test_an_anomaly_pointing_at_a_requirement_that_does_not_exist_is_rejected() -> None:
    """Un índice fuera de rango no admite lectura benigna: es inventado."""
    draft = good_draft()
    draft.anomalies[0].requirement_index = 9
    with pytest.raises(rules.ExtractionRejected, match="que no existe"):
        rules.validate(draft, ADVERT)


def test_an_anomalous_requirement_without_an_explanation_is_flagged() -> None:
    """Se registra, no se reetiqueta.

    La señal de que algo va mal en el anuncio sigue sirviendo al filtro
    automático de M2 aunque el modelo no haya dicho por qué.
    """
    draft = good_draft()
    draft.anomalies = []
    result = rules.validate(draft, ADVERT)

    assert result.requirements[3].kind is vocab.RequirementKind.ANOMALOUS
    assert "anomaly_without_explanation" in _rules_applied(result)


def test_an_anomaly_survives_the_loss_of_its_requirement() -> None:
    """Puede seguir siendo cierta del anuncio aunque su requisito se caiga."""
    draft = good_draft()
    draft.requirements[3].source_quote = "Diez años de experiencia con Marea"
    result = rules.validate(draft, ADVERT)

    assert len(result.requirements) == 3
    assert len(result.anomalies) == 1
    assert result.anomalies[0].requirement_position is None


# ---------------------------------------------------------------------------
# Valores que no pueden ser lo que dicen ser
# ---------------------------------------------------------------------------


def test_a_negative_amount_is_dropped() -> None:
    draft = good_draft()
    draft.compensation.amount_min.value = -38000.0
    result = rules.validate(draft, ADVERT)

    assert result.columns["comp_amount_min"] is None
    assert "negative_number" in _rules_applied(result)


def test_an_inverted_range_drops_both_ends() -> None:
    """No se arregla intercambiándolos: no hay forma de saber cuál sobra.

    Una horquilla invertida que se cuele envenena el scoring de M2 en
    silencio, que es peor que no tener horquilla.
    """
    draft = good_draft()
    draft.compensation.amount_min.value = 46000.0
    draft.compensation.amount_max.value = 38000.0
    result = rules.validate(draft, ADVERT)

    assert result.columns["comp_amount_min"] is None
    assert result.columns["comp_amount_max"] is None
    assert _rules_applied(result) == {"inverted_range"}


def test_a_currency_that_is_not_a_code_is_dropped() -> None:
    draft = good_draft()
    draft.compensation.currency.value = "euros"
    result = rules.validate(draft, ADVERT)

    assert result.columns["comp_currency"] is None
    assert "not_a_currency_code" in _rules_applied(result)


def test_a_lowercase_currency_code_is_normalised() -> None:
    draft = good_draft()
    draft.compensation.currency.value = "eur"
    result = rules.validate(draft, ADVERT)

    assert result.columns["comp_currency"] == "EUR"
    assert result.corrections == []


def test_responsibilities_absent_becomes_an_empty_list() -> None:
    """La columna es NOT NULL: la ausencia se guarda como lista vacía.

    Y la evidencia sigue diciendo `absent`, que es lo que distingue «el
    anuncio no cuenta las responsabilidades» de «no tiene ninguna».
    """
    draft = good_draft()
    draft.responsibilities = absent()
    result = rules.validate(draft, ADVERT)

    assert result.columns["responsibilities"] == []
    assert result.evidence["responsibilities"] == {"status": "absent"}


def test_an_empty_list_presented_as_published_is_dropped() -> None:
    draft = good_draft()
    draft.identification.language_of_work.value = ["", "  "]
    result = rules.validate(draft, ADVERT)

    assert result.columns["language_of_work"] is None
    assert "empty_list" in _rules_applied(result)


def test_numbers_are_stored_as_decimals() -> None:
    """Los importes salen del modelo como `number` y se guardan como NUMERIC.

    La conversión pasa por `str` a propósito: `Decimal(38000.0)` arrastraría
    el error binario del float.
    """
    from decimal import Decimal

    result = rules.validate(good_draft(), ADVERT)
    assert result.columns["comp_amount_min"] == Decimal("38000.0")
    assert isinstance(result.columns["experience_years_required"], Decimal)
