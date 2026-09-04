"""Guardar y leer la capa `assessment`.

Igual que el repositorio de ofertas de M1: ninguna función de aquí hace
`commit` —la frontera de la transacción la decide quien llama— y ninguna
valida nada. Lo que entra ya pasó por `rules.py` y por `scoring.py`, y esas
son las dos únicas puertas.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.assessment import vocabularies as vocab
from futuro_api.assessment.rules import ValidatedScoring, ValidatedVariant
from futuro_api.assessment.scoring import Computed
from futuro_api.jobs import repository as jobs_repo
from futuro_api.models import (
    AssessmentDimension,
    AssessmentGate,
    OfferAssessment,
    OfferCapture,
    OfferExtraction,
    RequirementMatchRow,
    VariantRecommendation,
)


async def save_assessment(
    session: AsyncSession,
    *,
    extraction_id: uuid.UUID,
    job_run_id: uuid.UUID | None,
    source: vocab.AssessmentSource,
    derived_from_id: uuid.UUID | None,
    scoring_model_version: str,
    scoring_model_sha256: str,
    prompt_version: str | None,
    model: str | None,
    validated: ValidatedScoring,
    computed: Computed,
    requirement_ids: dict[int, uuid.UUID],
) -> OfferAssessment:
    """Guarda un assessment nuevo. Nunca sobrescribe el anterior.

    Los hijos se cuelgan por la relación y no fijando `assessment_id` a
    mano, por lo mismo que en M1: SQLAlchemy ordena los INSERT, y el objeto
    que se devuelve trae sus colecciones cargadas, así que leerlas no
    dispara una consulta perezosa —que en código asíncrono no es una
    consulta lenta, es una excepción—.

    `requirement_ids` traduce posición de requisito a identificador de fila.
    Lo construye quien llama, que es el único que tiene la extracción
    delante; aquí no se consulta para no volver a leer lo que ya está en
    memoria.
    """
    assessment = OfferAssessment(
        extraction_id=extraction_id,
        job_run_id=job_run_id,
        source=source,
        derived_from_id=derived_from_id,
        scoring_model_version=scoring_model_version,
        scoring_model_sha256=scoring_model_sha256,
        prompt_version=prompt_version,
        model=model,
        value_score=computed.value_score,
        coverage=computed.coverage,
        probability_band=validated.probability_band,
        probability_reason=validated.probability_reason,
        portfolio_bucket=computed.portfolio_bucket,
        portfolio_note=computed.portfolio_note,
        effort_tier=computed.effort_tier,
        corrections=[correction.as_dict() for correction in validated.corrections],
    )

    for position, dimension in enumerate(validated.dimensions):
        assessment.dimensions.append(
            AssessmentDimension(
                position=position,
                dimension=dimension.name,
                weight=dimension.weight,
                score=dimension.score,
                citation=dimension.citation,
                reason=dimension.reason,
                anchor=dimension.anchor,
                unscored_reason=dimension.unscored_reason,
            )
        )

    for position, gate in enumerate(validated.gates):
        assessment.gates.append(
            AssessmentGate(
                position=position,
                gate=gate.name,
                status=gate.status,
                citation=gate.citation,
                reason=gate.reason,
            )
        )

    for match in validated.requirement_matches:
        requirement_id = requirement_ids.get(match.requirement_position)
        if requirement_id is None:  # pragma: no cover - `rules.py` ya lo filtra
            continue
        assessment.requirement_matches.append(
            RequirementMatchRow(
                requirement_id=requirement_id,
                match=match.match,
                evidence_ref=match.evidence_ref,
                # `cv_action` se queda nulo en M2: ver la cabecera de
                # `assessment/models.py`.
                cv_action=None,
                reason=match.reason,
            )
        )

    session.add(assessment)
    await session.flush()
    return assessment


async def save_variant_recommendation(
    session: AsyncSession,
    *,
    extraction_id: uuid.UUID,
    job_run_id: uuid.UUID | None,
    validated: ValidatedVariant,
    variants_guide_sha256: str,
    prompt_version: str,
    model: str,
) -> VariantRecommendation:
    recommendation = VariantRecommendation(
        extraction_id=extraction_id,
        job_run_id=job_run_id,
        variant=validated.variant,
        confidence=validated.confidence,
        reason=validated.reason,
        variants_guide_sha256=variants_guide_sha256,
        prompt_version=prompt_version,
        model=model,
    )
    session.add(recommendation)
    await session.flush()
    return recommendation


async def current_assessment(
    session: AsyncSession, extraction_id: uuid.UUID
) -> OfferAssessment | None:
    """El assessment vigente de una extracción: el último.

    Sin marca de «vigente» en la tabla, por lo mismo que en las
    extracciones: un flag mutable en una tabla inmutable es una
    contradicción que se paga tarde. El desempate por `id` hace la consulta
    determinista cuando dos filas comparten marca de tiempo, que pasa al
    repuntuar el histórico entero de golpe.
    """
    return (
        await session.execute(
            sa.select(OfferAssessment)
            .where(OfferAssessment.extraction_id == extraction_id)
            .order_by(OfferAssessment.assessed_at.desc(), OfferAssessment.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def current_variant_recommendation(
    session: AsyncSession, extraction_id: uuid.UUID
) -> VariantRecommendation | None:
    return (
        await session.execute(
            sa.select(VariantRecommendation)
            .where(VariantRecommendation.extraction_id == extraction_id)
            .order_by(
                VariantRecommendation.recommended_at.desc(),
                VariantRecommendation.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def assessment_versions(
    session: AsyncSession, extraction_id: uuid.UUID
) -> Sequence[OfferAssessment]:
    """Todas las puntuaciones de una extracción, de la más nueva a la más vieja.

    Es lo que hace visible que dos ofertas puntuadas con modelos de scoring
    distintos no son comparables: la fila vieja sigue ahí con su versión y
    su hash.
    """
    return (
        (
            await session.execute(
                sa.select(OfferAssessment)
                .where(OfferAssessment.extraction_id == extraction_id)
                .order_by(OfferAssessment.assessed_at.desc(), OfferAssessment.id.desc())
            )
        )
        .scalars()
        .all()
    )


async def cost_of_assessment(
    session: AsyncSession, assessment: OfferAssessment
) -> Decimal | None:
    """Lo que costaron las llamadas del trabajo que produjo un assessment.

    `None` y no cero cuando no hay trabajo: un assessment recalculado no
    costó nada porque no llamó a nadie, y eso no es lo mismo que «no
    consta». El cero sí aparece con el cliente simulado, que sí llama pero
    no cobra.
    """
    if assessment.job_run_id is None:
        return None
    return await jobs_repo.cost_of_run(session, assessment.job_run_id)


async def scorable_extractions(
    session: AsyncSession, *, limit: int, after: uuid.UUID | None = None
) -> Sequence[OfferExtraction]:
    """Las extracciones vigentes de todas las capturas, para repuntuar.

    Este es el recorrido que hace real la propiedad que justifica que
    `assessment` sea una capa aparte: repuntuar el histórico es barrer la
    base de datos, no volver a pagar la extracción de cada oferta.

    `DISTINCT ON (capture_id)` con el mismo orden que
    `offers.repository.current_extraction`, para que repuntuar no elija una
    extracción distinta de la que la pantalla llama vigente. Se pagina por
    `id` de captura y no por desplazamiento: el barrido puede tardar y una
    captura nueva en medio descuadraría un `OFFSET`.
    """
    current = (
        sa.select(
            OfferExtraction.id.label("extraction_id"),
            OfferCapture.id.label("capture_id"),
        )
        .join(OfferCapture, OfferCapture.id == OfferExtraction.capture_id)
        .distinct(OfferExtraction.capture_id)
        .order_by(
            OfferExtraction.capture_id,
            OfferExtraction.extracted_at.desc(),
            OfferExtraction.id.desc(),
        )
        .subquery()
    )
    query = (
        sa.select(OfferExtraction)
        .join(current, current.c.extraction_id == OfferExtraction.id)
        .order_by(current.c.capture_id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(current.c.capture_id > after)
    return (await session.execute(query)).scalars().all()
