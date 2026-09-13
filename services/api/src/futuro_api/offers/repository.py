"""Guardar y leer ofertas.

Ninguna función de aquí hace `commit`: la frontera de la transacción la
decide quien llama, que es el único que sabe si el trabajo terminó. Un
repositorio que commitea por su cuenta deja medias extracciones guardadas
cuando el paso siguiente falla.

Tampoco valida nada. Lo que entra aquí ya pasó por `rules.validate`, y esa
es la única puerta: si algún día alguien construye una fila de extracción
sin pasar por ahí, este módulo la guardará tal cual.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, NamedTuple

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.models import (
    Company,
    OfferAnomaly,
    OfferAssessment,
    OfferCapture,
    OfferExtraction,
    OfferRequirement,
    OfferStatusEvent,
)
from futuro_api.offers import rules
from futuro_api.offers import vocabularies as vocab
from futuro_api.pipeline.vocabularies import DEFAULT_STATUS, ApplicationStatus


def sha256_of(raw_text: str) -> str:
    """Huella del texto tal como llegó, sin normalizar nada.

    Sin normalizar a propósito: es la prueba de qué se recibió, así que dos
    pegadas que difieran en un espacio son dos textos distintos. La
    normalización es cosa de comparar citas, no de identificar capturas.
    """
    return hashlib.sha256(raw_text.encode()).hexdigest()


def normalise_company_name(name: str) -> str:
    """Clave de deduplicación de una empresa.

    Deliberadamente conservadora: minúsculas, espacios colapsados y la
    puntuación final fuera, y nada más. No se tocan los sufijos societarios,
    así que «Astillero Nube SL» y «Astillero Nube S.L.» quedan como dos
    filas. Es el error que se prefiere: dos filas para una empresa se
    arreglan fusionándolas, mientras que una fusión falsa mezcla dos
    empresas distintas y no se deshace.
    """
    return rules.normalise(name).rstrip(" .,;:·-")


async def find_capture_by_sha256(
    session: AsyncSession, raw_text_sha256: str
) -> OfferCapture | None:
    return (
        await session.execute(
            sa.select(OfferCapture).where(
                OfferCapture.raw_text_sha256 == raw_text_sha256
            )
        )
    ).scalar_one_or_none()


async def create_capture(
    session: AsyncSession,
    *,
    source: vocab.SourceChannel,
    raw_text: str,
    source_url: str | None = None,
    deadline: date | None = None,
    capture_note: str | None = None,
) -> OfferCapture:
    capture = OfferCapture(
        source=source,
        raw_text=raw_text,
        raw_text_sha256=sha256_of(raw_text),
        source_url=source_url,
        deadline=deadline,
        capture_note=capture_note,
    )
    session.add(capture)
    await session.flush()
    return capture


async def resolve_company(session: AsyncSession, name: str) -> Company:
    """Devuelve la fila de la empresa, creándola si no existe.

    El `ON CONFLICT DO NOTHING` no es paranoia: dos extracciones de la misma
    empresa pueden correr a la vez en el worker, y la constraint de
    `name_key` haría fallar a la segunda. Con esto, la segunda se encuentra
    la fila de la primera.
    """
    name_key = normalise_company_name(name)
    inserted = (
        await session.execute(
            pg_insert(Company)
            .values(name=name.strip(), name_key=name_key)
            .on_conflict_do_nothing(index_elements=[Company.name_key])
            .returning(Company.id)
        )
    ).scalar_one_or_none()
    if inserted is not None:
        return await session.get_one(Company, inserted)
    return (
        await session.execute(sa.select(Company).where(Company.name_key == name_key))
    ).scalar_one()


async def save_extraction(
    session: AsyncSession,
    *,
    capture_id: uuid.UUID,
    job_run_id: uuid.UUID | None,
    prompt_version: str,
    model: str,
    validated: rules.ValidatedExtraction,
) -> OfferExtraction:
    """Guarda una extracción nueva. Nunca sobrescribe la anterior.

    Es lo que hace que reextraer con otro prompt no destruya el histórico:
    la capa es inmutable, y la base de datos lo impone con un trigger, así
    que ni siquiera un `UPDATE` por descuido podría hacerlo.
    """
    posting = (
        await resolve_company(session, validated.posting_company_name)
        if validated.posting_company_name
        else None
    )
    employer = (
        await resolve_company(session, validated.employer_company_name)
        if validated.employer_company_name
        else None
    )

    extraction = OfferExtraction(
        capture_id=capture_id,
        job_run_id=job_run_id,
        prompt_version=prompt_version,
        model=model,
        evidence=validated.evidence,
        corrections=validated.corrections,
        posting_company_id=posting.id if posting else None,
        employer_company_id=employer.id if employer else None,
        employer_confidence=validated.employer_confidence,
        **validated.columns,
    )
    # Los hijos se cuelgan por la relación y no fijando `extraction_id` a
    # mano. Así SQLAlchemy resuelve el orden de los INSERT y las claves
    # ajenas por su cuenta, y —lo que importa aquí— el objeto que se
    # devuelve ya trae sus colecciones cargadas: leerlas no dispara una
    # consulta perezosa, que en código asíncrono no es una consulta lenta
    # sino una excepción.
    by_position: dict[int, OfferRequirement] = {}
    for validated_requirement in validated.requirements:
        requirement = OfferRequirement(
            position=validated_requirement.position,
            text=validated_requirement.text,
            source_quote=validated_requirement.source_quote,
            kind=validated_requirement.kind,
            category=validated_requirement.category,
            match=validated_requirement.match,
            evidence_ref=validated_requirement.evidence_ref,
            cv_action=validated_requirement.cv_action,
        )
        extraction.requirements.append(requirement)
        by_position[validated_requirement.position] = requirement

    for validated_anomaly in validated.anomalies:
        anomaly = OfferAnomaly(
            position=validated_anomaly.position,
            text=validated_anomaly.text,
            explanation=validated_anomaly.explanation,
            source_quote=validated_anomaly.source_quote,
        )
        if validated_anomaly.requirement_position is not None:
            anomaly.requirement = by_position.get(
                validated_anomaly.requirement_position
            )
        extraction.anomalies.append(anomaly)

    session.add(extraction)
    await session.flush()
    return extraction


async def current_extraction(
    session: AsyncSession, capture_id: uuid.UUID
) -> OfferExtraction | None:
    """La extracción vigente de una captura: la última.

    No hay marca de «vigente» en la tabla —sería un campo mutable en una
    capa inmutable— así que vigente es la más reciente. El desempate por
    `id` hace la consulta determinista cuando dos extracciones comparten
    marca de tiempo, que pasa si se reextrae dos veces en el mismo
    milisegundo.
    """
    return (
        await session.execute(
            sa.select(OfferExtraction)
            .where(OfferExtraction.capture_id == capture_id)
            .order_by(OfferExtraction.extracted_at.desc(), OfferExtraction.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def extraction_versions(
    session: AsyncSession, capture_id: uuid.UUID
) -> Sequence[OfferExtraction]:
    """Todas las versiones, de la más nueva a la más vieja."""
    return (
        (
            await session.execute(
                sa.select(OfferExtraction)
                .where(OfferExtraction.capture_id == capture_id)
                .order_by(
                    OfferExtraction.extracted_at.desc(), OfferExtraction.id.desc()
                )
            )
        )
        .scalars()
        .all()
    )


SortField = Literal["captured_at", "value_score", "title", "company"]
SortOrder = Literal["asc", "desc"]


class OfferListRow(NamedTuple):
    """Una fila de la pantalla Pipeline: solo columnas, no entidades enteras.

    Cargar `OfferExtraction`/`OfferAssessment` completos -con sus relaciones
    `selectin`- para pintar siete columnas de una tabla sería pagar por
    `requirements`, `dimensions`, `gates`... de las cien filas de la página,
    y nada de eso se enseña aquí. `extraction_id`/`assessment_id` viajan
    solo como el «existe o no» que pide `views.status_of`, no para leer nada
    más de ellos.
    """

    id: uuid.UUID
    captured_at: datetime
    title: str | None
    company: str | None
    posting_status: vocab.PostingStatus | None
    extraction_id: uuid.UUID | None
    assessment_id: uuid.UUID | None
    value_score: Decimal | None
    probability_band: data_vocab.ProbabilityBand | None
    portfolio_bucket: data_vocab.PortfolioBucket | None
    status: ApplicationStatus


async def list_offer_rows(
    session: AsyncSession,
    *,
    limit: int,
    status: ApplicationStatus | None = None,
    posting_status: vocab.PostingStatus | None = None,
    portfolio_bucket: data_vocab.PortfolioBucket | None = None,
    sort: SortField = "captured_at",
    order: SortOrder = "desc",
) -> Sequence[OfferListRow]:
    """La tabla densa del Pipeline: filtro, orden y límite en una sola consulta.

    Sin paginación por cursor -micro-decisión acordada con Pablo el
    2026-09-13: todo cabe en el límite de `MAX_PAGE`, y filtrar u ordenar
    después de traer una página fija de capturas por `captured_at`
    descuadraría el resultado, que es justo lo que un `before` evitaba para
    ese único orden-. Con filtro y orden configurables, el corte tiene que
    hacerse en la propia consulta SQL: de ahí que esto ya no sea "capturas,
    con la extracción vigente pegada en Python" sino un único `LEFT JOIN`
    contra la extracción, el assessment y el estado vigentes de cada uno,
    cada uno resuelto con el mismo `DISTINCT ON` que su propio módulo usa
    para no discrepar con el detalle de una oferta.
    """
    current_extraction = (
        sa.select(
            OfferExtraction.capture_id.label("capture_id"),
            OfferExtraction.id.label("extraction_id"),
            OfferExtraction.title.label("title"),
            OfferExtraction.posting_status.label("posting_status"),
            OfferExtraction.posting_company_id.label("posting_company_id"),
            OfferExtraction.employer_company_id.label("employer_company_id"),
        )
        .distinct(OfferExtraction.capture_id)
        .order_by(
            OfferExtraction.capture_id,
            OfferExtraction.extracted_at.desc(),
            OfferExtraction.id.desc(),
        )
        .subquery()
    )
    current_assessment = (
        sa.select(
            OfferAssessment.extraction_id.label("extraction_id"),
            OfferAssessment.id.label("assessment_id"),
            OfferAssessment.value_score.label("value_score"),
            OfferAssessment.probability_band.label("probability_band"),
            OfferAssessment.portfolio_bucket.label("portfolio_bucket"),
        )
        .distinct(OfferAssessment.extraction_id)
        .order_by(
            OfferAssessment.extraction_id,
            OfferAssessment.assessed_at.desc(),
            OfferAssessment.id.desc(),
        )
        .subquery()
    )
    current_status = (
        sa.select(
            OfferStatusEvent.capture_id.label("capture_id"),
            OfferStatusEvent.status.label("status"),
        )
        .distinct(OfferStatusEvent.capture_id)
        .order_by(
            OfferStatusEvent.capture_id,
            OfferStatusEvent.occurred_at.desc(),
            OfferStatusEvent.id.desc(),
        )
        .subquery()
    )

    # El empleador final manda sobre quien publica -es la empresa para la
    # que se trabajaría, lo que interesa de un vistazo-, mismo criterio que
    # el listado anterior aplicaba en Python.
    posting_company = aliased(Company)
    employer_company = aliased(Company)
    company_name = sa.func.coalesce(employer_company.name, posting_company.name)
    status_column = sa.func.coalesce(current_status.c.status, DEFAULT_STATUS)

    query = (
        sa.select(
            OfferCapture.id.label("id"),
            OfferCapture.captured_at.label("captured_at"),
            current_extraction.c.title,
            company_name.label("company"),
            current_extraction.c.posting_status,
            current_extraction.c.extraction_id,
            current_assessment.c.assessment_id,
            current_assessment.c.value_score,
            current_assessment.c.probability_band,
            current_assessment.c.portfolio_bucket,
            status_column.label("status"),
        )
        .select_from(OfferCapture)
        .outerjoin(
            current_extraction, current_extraction.c.capture_id == OfferCapture.id
        )
        .outerjoin(
            current_assessment,
            current_assessment.c.extraction_id == current_extraction.c.extraction_id,
        )
        .outerjoin(
            posting_company,
            posting_company.id == current_extraction.c.posting_company_id,
        )
        .outerjoin(
            employer_company,
            employer_company.id == current_extraction.c.employer_company_id,
        )
        .outerjoin(current_status, current_status.c.capture_id == OfferCapture.id)
    )

    if status is not None:
        query = query.where(status_column == status)
    if posting_status is not None:
        query = query.where(current_extraction.c.posting_status == posting_status)
    if portfolio_bucket is not None:
        query = query.where(current_assessment.c.portfolio_bucket == portfolio_bucket)

    # `Any` y no `sa.ColumnElement[Any]`: `OfferCapture.captured_at` es un
    # `InstrumentedAttribute`, no un `ColumnElement`, a ojos de los stubs de
    # tipos de SQLAlchemy, aunque las dos cosas se comporten igual en
    # `sa.asc`/`sa.desc`.
    sort_columns: dict[SortField, Any] = {
        "captured_at": OfferCapture.captured_at,
        "value_score": current_assessment.c.value_score,
        "title": current_extraction.c.title,
        "company": company_name,
    }
    direction = sa.asc if order == "asc" else sa.desc
    ordered = direction(sort_columns[sort])
    if sort == "value_score":
        # Sin puntuar va siempre al final, sea cual sea el sentido del
        # orden: micro-decisión acordada con Pablo el 2026-09-13, para que
        # "ordenar de peor a mejor" no ponga las ofertas sin puntuar por
        # delante de las que sí puntúan bajo.
        ordered = sa.nulls_last(ordered)
    query = query.order_by(ordered, OfferCapture.id.desc()).limit(limit)

    rows = (await session.execute(query)).all()
    return [OfferListRow(*row) for row in rows]
