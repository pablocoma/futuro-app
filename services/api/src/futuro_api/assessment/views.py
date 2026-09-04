"""Lo que la API devuelve de la capa `assessment`.

Un principio de esta rebanada que llega hasta el navegador: **el frontend no
hace aritmética**. Recibe el peso y la fracción de peso ya calculados, y la
nota ya normalizada a la altura de la barra. Si la pantalla dividiera pesos
para sacar anchos, habría dos sitios donde se calcula lo mismo, y el día que
discreparan el dibujo diría una cosa y la puntuación otra.

`weight_share` y `score_share` salen como número y no como cadena, al
contrario que `value_score` y `coverage`. La diferencia es a qué sirven: los
dos primeros son geometría —el ancho y el alto de un rectángulo en CSS— y
los dos últimos son la puntuación, que se enseña tal cual y no se recalcula,
así que viaja como el texto exacto que hay en la base de datos. Es la misma
regla que M1 aplicó a los importes.

Este módulo importa `CorrectionView` de `offers.views` y no al revés: la
dirección de las dependencias es `assessment` → `offers`, la misma que en
`rules.py`. La composición de las dos mitades la hace el router, que es el
único que ve las dos.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from futuro_api.assessment import vocabularies as vocab
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.models import (
    OfferAssessment,
    VariantRecommendation,
)
from futuro_api.offers import vocabularies as offers_vocab
from futuro_api.offers.views import CorrectionView

# Mismo juego de estados que la extracción, y por el mismo motivo: la
# pantalla tiene que poder decir «en cola» mientras hay una puntuación
# anterior a la vista.
AssessmentStatus = Literal["none", "queued", "running", "succeeded", "failed"]

# La escala del modelo de scoring. Está aquí porque la altura de la barra es
# la nota dividida por el máximo, y ese máximo está en un CHECK del esquema
# —no en el YAML, que el cargador obliga a que coincida—.
SCORE_MAX = 5


class DimensionView(BaseModel):
    """Una barra de la composición ponderada.

    `weight_share` es el ancho y `score_share` la altura. El ancho se
    calcula sobre el peso **total** del modelo de scoring y no sobre el
    renormalizado: la barra ancha y vacía de una dimensión sin puntuar es
    justamente lo que enseña cuánto peso se perdió. La renormalización se ve
    en `value_score` y en `coverage`, no en los anchos.
    """

    dimension: str
    weight: int
    weight_share: float
    score: int | None = None
    score_share: float | None = None
    citation: str | None = None
    reason: str | None = None
    # El ancla escrita del modelo de scoring que justifica esta nota, tal
    # como estaba al puntuar. Sale de la fila y no del YAML de hoy.
    anchor: str | None = None
    unscored_reason: str | None = None


class GateView(BaseModel):
    gate: str
    status: vocab.GateStatus
    citation: str | None = None
    reason: str


class RequirementMatchView(BaseModel):
    """El cruce de un requisito contra el banco de evidencias.

    Lleva el texto del requisito además de su posición para que la pantalla
    no tenga que cruzar dos listas por índice, que es la clase de cosa que
    se desalinea en cuanto una de las dos se filtra.
    """

    requirement_position: int
    requirement_text: str
    match: offers_vocab.RequirementMatch
    evidence_ref: str | None = None
    reason: str


class AssessmentView(BaseModel):
    id: uuid.UUID
    assessed_at: datetime
    source: vocab.AssessmentSource
    scoring_model_version: str
    scoring_model_sha256: str
    prompt_version: str | None = None
    model: str | None = None
    cost_usd: str | None = None
    value_score: str | None = None
    coverage: str
    probability_band: data_vocab.ProbabilityBand
    probability_reason: str
    portfolio_bucket: data_vocab.PortfolioBucket | None = None
    portfolio_note: str | None = None
    effort_tier: data_vocab.EffortTier
    dimensions: list[DimensionView]
    gates: list[GateView]
    requirement_matches: list[RequirementMatchView]
    corrections: list[CorrectionView]


class VariantRecommendationView(BaseModel):
    variant: str
    confidence: offers_vocab.Confidence
    reason: str
    recommended_at: datetime
    model: str
    prompt_version: str


class AssessmentVersionView(BaseModel):
    """Una puntuación anterior, para que se vea que hubo otras.

    Es lo que hace visible que dos ofertas puntuadas con modelos de scoring
    distintos no son comparables: la fila vieja sigue ahí con su versión.
    """

    id: uuid.UUID
    assessed_at: datetime
    source: vocab.AssessmentSource
    scoring_model_version: str
    value_score: str | None = None


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def assessment_view(
    assessment: OfferAssessment,
    *,
    total_weight: int,
    requirement_texts: dict[uuid.UUID, tuple[int, str]],
    cost_usd: Decimal | None,
) -> AssessmentView:
    """Traduce una fila de assessment a lo que la pantalla necesita.

    `total_weight` se calcula sumando los pesos **de las filas guardadas** y
    no leyendo el YAML de hoy. Es lo que hace que la composición de una
    oferta puntuada hace meses siga sumando 100% con sus propios pesos, en
    vez de descuadrarse porque el modelo de scoring haya cambiado desde
    entonces.
    """
    share = float(total_weight) if total_weight > 0 else 1.0
    return AssessmentView(
        id=assessment.id,
        assessed_at=assessment.assessed_at,
        source=assessment.source,
        scoring_model_version=assessment.scoring_model_version,
        scoring_model_sha256=assessment.scoring_model_sha256,
        prompt_version=assessment.prompt_version,
        model=assessment.model,
        cost_usd=_decimal(cost_usd),
        value_score=_decimal(assessment.value_score),
        coverage=format(assessment.coverage, "f"),
        probability_band=assessment.probability_band,
        probability_reason=assessment.probability_reason,
        portfolio_bucket=assessment.portfolio_bucket,
        portfolio_note=assessment.portfolio_note,
        effort_tier=assessment.effort_tier,
        dimensions=[
            DimensionView(
                dimension=row.dimension,
                weight=row.weight,
                weight_share=round(row.weight / share, 4),
                score=row.score,
                score_share=(
                    round(row.score / SCORE_MAX, 4) if row.score is not None else None
                ),
                citation=row.citation,
                reason=row.reason,
                anchor=row.anchor,
                unscored_reason=row.unscored_reason,
            )
            for row in assessment.dimensions
        ],
        gates=[
            GateView(
                gate=row.gate,
                status=row.status,
                citation=row.citation,
                reason=row.reason,
            )
            for row in assessment.gates
        ],
        requirement_matches=[
            RequirementMatchView(
                requirement_position=requirement_texts[row.requirement_id][0],
                requirement_text=requirement_texts[row.requirement_id][1],
                match=row.match,
                evidence_ref=row.evidence_ref,
                reason=row.reason,
            )
            for row in assessment.requirement_matches
            if row.requirement_id in requirement_texts
        ],
        corrections=[
            CorrectionView(**correction) for correction in assessment.corrections
        ],
    )


def variant_view(
    recommendation: VariantRecommendation,
) -> VariantRecommendationView:
    return VariantRecommendationView(
        variant=recommendation.variant,
        confidence=recommendation.confidence,
        reason=recommendation.reason,
        recommended_at=recommendation.recommended_at,
        model=recommendation.model,
        prompt_version=recommendation.prompt_version,
    )


def total_weight_of(assessment: OfferAssessment) -> int:
    return sum(row.weight for row in assessment.dimensions)
