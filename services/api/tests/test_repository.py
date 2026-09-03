"""Guardar y leer ofertas, contra Postgres de verdad.

Estos tests usan la sesión transaccional: el repositorio hace `flush` y no
`commit`, así que todo lo que escriben se deshace al terminar.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.models import (
    Company,
    OfferAnomaly,
    OfferCapture,
    OfferRequirement,
)
from futuro_api.offers import prompt, rules
from futuro_api.offers import repository as repo
from futuro_api.offers import vocabularies as vocab
from tests.synthetic import ADVERT, absent, good_draft


async def _capture(session: AsyncSession, text: str = ADVERT) -> OfferCapture:
    return await repo.create_capture(
        session, source=vocab.SourceChannel.PASTE, raw_text=text
    )


# ---------------------------------------------------------------------------
# Identidad de una captura
# ---------------------------------------------------------------------------


def test_the_hash_is_of_the_text_exactly_as_it_arrived() -> None:
    """Sin normalizar: es la prueba de qué se recibió.

    Dos pegadas que difieren en un espacio son dos textos distintos. La
    normalización es cosa de comparar citas, no de identificar capturas.
    """
    assert repo.sha256_of("Ingeniero de Datos") != repo.sha256_of("Ingeniero  de Datos")
    assert repo.sha256_of(ADVERT) == repo.sha256_of(ADVERT)


async def test_a_capture_is_found_by_its_hash(session: AsyncSession) -> None:
    capture = await _capture(session)
    found = await repo.find_capture_by_sha256(session, repo.sha256_of(ADVERT))
    assert found is not None
    assert found.id == capture.id


async def test_an_unknown_hash_finds_nothing(session: AsyncSession) -> None:
    assert await repo.find_capture_by_sha256(session, "0" * 64) is None


# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------


def test_the_company_key_ignores_case_and_spacing() -> None:
    assert repo.normalise_company_name("  Astillero   NUBE  ") == (
        repo.normalise_company_name("astillero nube")
    )


def test_the_company_key_does_not_touch_legal_suffixes() -> None:
    """Deliberadamente conservador, y el test lo fija.

    «Astillero Nube SL» y «Astillero Nube S.L.» quedan como dos filas. Es el
    error que se prefiere: dos filas para una empresa se arreglan
    fusionándolas, mientras que una fusión falsa mezcla dos empresas
    distintas y no se deshace.
    """
    assert repo.normalise_company_name("Astillero Nube SL") != (
        repo.normalise_company_name("Astillero Nube S.L.")
    )


async def test_a_company_is_created_once_and_reused(session: AsyncSession) -> None:
    first = await repo.resolve_company(session, "Astillero Nube")
    second = await repo.resolve_company(session, "  ASTILLERO   nube ")
    assert first.id == second.id
    total = (
        await session.execute(sa.select(sa.func.count()).select_from(Company))
    ).scalar_one()
    assert total == 1
    # Se guarda el nombre tal como llegó la primera vez, no normalizado: la
    # clave es para deduplicar, no para enseñar.
    assert first.name == "Astillero Nube"


# ---------------------------------------------------------------------------
# Guardar una extracción
# ---------------------------------------------------------------------------


async def test_an_extraction_is_saved_whole(session: AsyncSession) -> None:
    capture = await _capture(session)
    validated = rules.validate(good_draft(), ADVERT)

    extraction = await repo.save_extraction(
        session,
        capture_id=capture.id,
        job_run_id=None,
        prompt_version=prompt.PROMPT_VERSION,
        model="stub",
        validated=validated,
    )

    assert extraction.title == "Ingeniero de Datos"
    assert extraction.role_family is vocab.RoleFamily.DATA_ENGINEER
    assert extraction.posting_status is vocab.PostingStatus.UNVERIFIABLE
    # La regla del contrato queda satisfecha sin que nadie ponga la fecha:
    # el código nunca acepta `active_verified` de un texto pegado.
    assert extraction.status_checked_at is None
    assert extraction.evidence["title"]["source_quote"] == "Ingeniero de Datos"
    assert extraction.corrections == []
    assert len(extraction.requirements) == 4
    assert len(extraction.anomalies) == 1


async def test_the_two_companies_are_saved_as_two_rows(
    session: AsyncSession,
) -> None:
    capture = await _capture(session)
    validated = rules.validate(good_draft(), ADVERT)

    extraction = await repo.save_extraction(
        session,
        capture_id=capture.id,
        job_run_id=None,
        prompt_version=prompt.PROMPT_VERSION,
        model="stub",
        validated=validated,
    )

    assert extraction.posting_company_id != extraction.employer_company_id
    assert extraction.employer_confidence is vocab.EmployerConfidence.HIGH
    posting = await session.get(Company, extraction.posting_company_id)
    employer = await session.get(Company, extraction.employer_company_id)
    assert posting is not None and posting.name == "Reclutamiento Bahía"
    assert employer is not None and employer.name == "Astillero Nube S.L."


async def test_an_anomaly_keeps_the_link_to_its_requirement(
    session: AsyncSession,
) -> None:
    capture = await _capture(session)
    validated = rules.validate(good_draft(), ADVERT)
    extraction = await repo.save_extraction(
        session,
        capture_id=capture.id,
        job_run_id=None,
        prompt_version=prompt.PROMPT_VERSION,
        model="stub",
        validated=validated,
    )

    anomaly = (
        await session.execute(
            sa.select(OfferAnomaly).where(OfferAnomaly.extraction_id == extraction.id)
        )
    ).scalar_one()
    requirement = await session.get(OfferRequirement, anomaly.requirement_id)
    assert requirement is not None
    assert requirement.kind is vocab.RequirementKind.ANOMALOUS


async def test_an_offer_without_named_companies_saves_nulls(
    session: AsyncSession,
) -> None:
    capture = await _capture(session)
    draft = good_draft()
    draft.companies.posting = draft.companies.employer = absent()
    draft.companies.employer_confidence = None
    validated = rules.validate(draft, ADVERT)

    extraction = await repo.save_extraction(
        session,
        capture_id=capture.id,
        job_run_id=None,
        prompt_version=prompt.PROMPT_VERSION,
        model="stub",
        validated=validated,
    )
    assert extraction.posting_company_id is None
    assert extraction.employer_company_id is None
    assert extraction.employer_confidence is None


# ---------------------------------------------------------------------------
# Versiones
# ---------------------------------------------------------------------------


async def test_reextracting_adds_a_row_and_keeps_the_old_one(
    session: AsyncSession,
) -> None:
    """Es la propiedad que justifica versionar la capa por prompt."""
    capture = await _capture(session)
    validated = rules.validate(good_draft(), ADVERT)

    first = await repo.save_extraction(
        session,
        capture_id=capture.id,
        job_run_id=None,
        prompt_version="offer-extraction/vieja",
        model="stub",
        validated=validated,
    )
    second = await repo.save_extraction(
        session,
        capture_id=capture.id,
        job_run_id=None,
        prompt_version="offer-extraction/nueva",
        model="stub",
        validated=validated,
    )

    versions = await repo.extraction_versions(
        session,
        capture.id,
    )
    assert [v.id for v in versions] == [second.id, first.id]
    current = await repo.current_extraction(
        session,
        capture.id,
    )
    assert current is not None
    assert current.id == second.id
    assert current.prompt_version == "offer-extraction/nueva"


async def test_a_capture_without_extractions_has_no_current_one(
    session: AsyncSession,
) -> None:
    capture = await _capture(session)
    assert (
        await repo.current_extraction(
            session,
            capture.id,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------


async def test_captures_are_listed_newest_first_and_paginate(
    session: AsyncSession,
) -> None:
    """La paginación va por la captura ancla y no por desplazamiento.

    Un `OFFSET` se descuadra en cuanto entra una oferta nueva mientras
    alguien mira la segunda página: se repite o se salta una fila.
    """
    first = await _capture(session, "Primer anuncio inventado, el más viejo.")
    second = await _capture(session, "Segundo anuncio inventado.")
    third = await _capture(session, "Tercer anuncio inventado, el más nuevo.")

    listed = await repo.list_captures(session, limit=10)
    assert [c.id for c in listed] == [third.id, second.id, first.id]

    page = await repo.list_captures(session, limit=10, before=third.id)
    assert [c.id for c in page] == [second.id, first.id]
