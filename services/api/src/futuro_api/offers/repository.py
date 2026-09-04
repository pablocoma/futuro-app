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
from datetime import date

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.models import (
    Company,
    OfferAnomaly,
    OfferCapture,
    OfferExtraction,
    OfferRequirement,
)
from futuro_api.offers import rules
from futuro_api.offers import vocabularies as vocab


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


async def list_captures(
    session: AsyncSession, *, limit: int = 50, before: uuid.UUID | None = None
) -> Sequence[OfferCapture]:
    """Capturas de la más reciente a la más antigua.

    `before` pagina por la captura que se pasó: se usa su `captured_at` en
    lugar de un desplazamiento, que se descuadra en cuanto entra una oferta
    nueva mientras alguien mira la segunda página.
    """
    query = sa.select(OfferCapture).order_by(
        OfferCapture.captured_at.desc(), OfferCapture.id.desc()
    )
    if before is not None:
        anchor = (
            sa.select(OfferCapture.captured_at, OfferCapture.id)
            .where(OfferCapture.id == before)
            .subquery()
        )
        query = query.where(
            sa.tuple_(OfferCapture.captured_at, OfferCapture.id)
            < sa.tuple_(anchor.c.captured_at, anchor.c.id)
        )
    return (await session.execute(query.limit(limit))).scalars().all()


async def current_extractions_for(
    session: AsyncSession, capture_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, OfferExtraction]:
    """La extracción vigente de cada captura, en una sola consulta.

    `DISTINCT ON` con el mismo orden que `current_extraction`, para que el
    listado y el detalle no puedan discrepar sobre cuál es la vigente.
    """
    if not capture_ids:
        return {}
    rows = (
        (
            await session.execute(
                sa.select(OfferExtraction)
                .where(OfferExtraction.capture_id.in_(capture_ids))
                .distinct(OfferExtraction.capture_id)
                .order_by(
                    OfferExtraction.capture_id,
                    OfferExtraction.extracted_at.desc(),
                    OfferExtraction.id.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.capture_id: row for row in rows}
