"""Lo que el esquema tiene que impedir por sí solo.

Estos tests no comprueban código de la aplicación: comprueban constraints y
triggers de Postgres. Existen porque las prohibiciones del contrato de datos
(`Futuro/docs/OFFER_DATA_CONTRACT.md`) se validan en Python *y* se sostienen
en la base de datos, y la mitad de abajo no la cubre ningún test de Python.

Todos los anuncios de estos tests son inventados. En este repositorio no
entran datos personales ni ofertas reales, tampoco en fixtures.
"""

from __future__ import annotations

import re
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from futuro_api.db import Base
from futuro_api.models import (
    OfferAnomaly,
    OfferCapture,
    OfferExtraction,
    OfferRequirement,
)
from futuro_api.offers import vocabularies as vocab

ANUNCIO = (
    "Astillero Nube busca Ingeniero de Datos para su equipo de Sevilla. "
    "Imprescindible SQL y tres años de experiencia. Se valora Python. "
    "Modalidad híbrida, dos días en oficina."
)


async def _insert_capture(
    connection: AsyncConnection, *, sha: str | None = None
) -> uuid.UUID:
    result = await connection.execute(
        sa.text(
            "INSERT INTO offer_captures (source, raw_text, raw_text_sha256) "
            "VALUES ('paste', :texto, :sha) RETURNING id"
        ),
        {"texto": ANUNCIO, "sha": sha or "a" * 64},
    )
    return result.scalar_one()  # type: ignore[no-any-return]


async def _insert_extraction(
    connection: AsyncConnection, capture_id: uuid.UUID
) -> uuid.UUID:
    result = await connection.execute(
        sa.text(
            "INSERT INTO offer_extractions "
            "(capture_id, prompt_version, model, evidence, posting_status) "
            "VALUES (:capture, 'test/0', 'stub', '{}', 'unverifiable') "
            "RETURNING id"
        ),
        {"capture": capture_id},
    )
    return result.scalar_one()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Vocabularios cerrados
# ---------------------------------------------------------------------------


def _vocabulary_columns() -> list[tuple[str, str, frozenset[str]]]:
    """Cada columna de vocabulario, con el nombre de su CHECK y sus valores.

    El nombre se compone con la convención de `db.NAMING_CONVENTION`. Que el
    test lo encuentre en la base de datos es, de paso, la comprobación de
    que esa convención sigue vigente.
    """
    columns = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.Enum):
                columns.append(
                    (
                        f"ck_{table.name}_{column.type.name}",
                        f"{table.name}.{column.name}",
                        frozenset(column.type.enums),
                    )
                )
    return columns


VOCABULARY_COLUMNS = _vocabulary_columns()


def test_there_are_vocabulary_columns_to_check() -> None:
    """Guarda contra una parametrización vacía, que pasaría en verde."""
    assert len(VOCABULARY_COLUMNS) >= 15


@pytest.mark.parametrize(
    ("constraint", "column", "values"),
    VOCABULARY_COLUMNS,
    ids=[column for _, column, _ in VOCABULARY_COLUMNS],
)
async def test_vocabularies_match_the_database(
    connection: AsyncConnection,
    constraint: str,
    column: str,
    values: frozenset[str],
) -> None:
    """El CHECK de cada vocabulario tiene exactamente los valores del StrEnum.

    Es el test que sostiene el filtro `include_name` de `migrations/env.py`:
    esos CHECK quedan fuera de la comparación de Alembic, así que ampliar un
    vocabulario y olvidar la migración no aparecería como deriva de esquema.
    Aquí sí aparece, y además compara los valores, no solo la existencia.
    """
    definition = (
        await connection.execute(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = :name"
            ),
            {"name": constraint},
        )
    ).scalar_one_or_none()
    assert definition is not None, f"falta el CHECK {constraint} para {column}"
    assert frozenset(re.findall(r"'([^']*)'::", definition)) == values


# ---------------------------------------------------------------------------
# Inmutabilidad
# ---------------------------------------------------------------------------


async def test_a_capture_cannot_be_updated(connection: AsyncConnection) -> None:
    capture_id = await _insert_capture(connection)
    with pytest.raises(IntegrityError, match="inmutable"):
        await connection.execute(
            sa.text("UPDATE offer_captures SET capture_note = 'x' WHERE id = :id"),
            {"id": capture_id},
        )


async def test_an_extraction_cannot_be_updated(connection: AsyncConnection) -> None:
    capture_id = await _insert_capture(connection)
    extraction_id = await _insert_extraction(connection, capture_id)
    with pytest.raises(IntegrityError, match="inmutable"):
        await connection.execute(
            sa.text("UPDATE offer_extractions SET model = 'otro' WHERE id = :id"),
            {"id": extraction_id},
        )


async def test_a_job_run_can_be_updated(connection: AsyncConnection) -> None:
    """La mitad operativa sí es mutable: un job cambia de estado.

    El trigger cubre las capas del contrato y solo esas; si algún día se
    extendiera a `job_runs`, la cola dejaría de poder avanzar.
    """
    job_id = (
        await connection.execute(
            sa.text(
                "INSERT INTO job_runs (kind, status) "
                "VALUES ('offer_extraction', 'queued') RETURNING id"
            )
        )
    ).scalar_one()
    await connection.execute(
        sa.text("UPDATE job_runs SET status = 'running' WHERE id = :id"),
        {"id": job_id},
    )


async def test_a_capture_can_be_deleted_and_takes_its_layers(
    connection: AsyncConnection,
) -> None:
    """Inmutable no es imborrable: un texto pegado por error se puede tirar."""
    capture_id = await _insert_capture(connection)
    extraction_id = await _insert_extraction(connection, capture_id)
    await connection.execute(
        sa.text(
            "INSERT INTO offer_requirements "
            "(extraction_id, position, text, source_quote, kind, category) "
            "VALUES (:e, 1, 'SQL', 'Imprescindible SQL', 'mandatory', 'technology')"
        ),
        {"e": extraction_id},
    )
    await connection.execute(
        sa.text("DELETE FROM offer_captures WHERE id = :id"), {"id": capture_id}
    )
    remaining = (
        await connection.execute(
            sa.text(
                "SELECT (SELECT count(*) FROM offer_extractions) "
                "+ (SELECT count(*) FROM offer_requirements)"
            )
        )
    ).scalar_one()
    assert remaining == 0


# ---------------------------------------------------------------------------
# Las prohibiciones del contrato
# ---------------------------------------------------------------------------


async def test_the_same_text_cannot_be_captured_twice(
    connection: AsyncConnection,
) -> None:
    """`raw_text_sha256` es único: es lo que detecta una reingesta."""
    await _insert_capture(connection)
    with pytest.raises(IntegrityError, match="raw_text_sha256"):
        await _insert_capture(connection)


async def test_an_empty_capture_is_rejected(connection: AsyncConnection) -> None:
    with pytest.raises(IntegrityError, match="raw_text_not_empty"):
        await connection.execute(
            sa.text(
                "INSERT INTO offer_captures (source, raw_text, raw_text_sha256) "
                "VALUES ('paste', '', :sha)"
            ),
            {"sha": "b" * 64},
        )


async def test_active_verified_needs_a_checked_at(
    connection: AsyncConnection,
) -> None:
    """Nunca una oferta activa sin haber comprobado que lo está."""
    capture_id = await _insert_capture(connection)
    with pytest.raises(IntegrityError, match="active_verified_needs_checked_at"):
        await connection.execute(
            sa.text(
                "INSERT INTO offer_extractions "
                "(capture_id, prompt_version, model, evidence, posting_status) "
                "VALUES (:c, 'test/0', 'stub', '{}', 'active_verified')"
            ),
            {"c": capture_id},
        )


async def test_an_inferred_employer_needs_its_confidence(
    connection: AsyncConnection,
) -> None:
    """Quien publica y el empleador final son dos referencias distintas.

    Y la segunda, cuando existe, no puede registrarse como un hecho: lleva
    siempre con cuánta confianza se afirma.
    """
    capture_id = await _insert_capture(connection)
    company_id = (
        await connection.execute(
            sa.text(
                "INSERT INTO companies (name, name_key) "
                "VALUES ('Astillero Nube SL', 'astillero nube sl') RETURNING id"
            )
        )
    ).scalar_one()
    with pytest.raises(IntegrityError, match="employer_needs_confidence"):
        await connection.execute(
            sa.text(
                "INSERT INTO offer_extractions (capture_id, prompt_version, model, "
                "evidence, posting_status, employer_company_id) "
                "VALUES (:c, 'test/0', 'stub', '{}', 'unverifiable', :company)"
            ),
            {"c": capture_id, "company": company_id},
        )


async def test_meets_without_an_evidence_ref_is_rejected(
    connection: AsyncConnection,
) -> None:
    """La prohibición central: sin referencia no se puede afirmar que cumple."""
    capture_id = await _insert_capture(connection)
    extraction_id = await _insert_extraction(connection, capture_id)
    with pytest.raises(IntegrityError, match="meets_needs_evidence_ref"):
        await connection.execute(
            sa.text(
                "INSERT INTO offer_requirements (extraction_id, position, text, "
                "source_quote, kind, category, match) VALUES "
                "(:e, 1, 'SQL', 'Imprescindible SQL', 'mandatory', 'technology', "
                "'meets')"
            ),
            {"e": extraction_id},
        )


async def test_partial_without_an_evidence_ref_is_allowed(
    connection: AsyncConnection,
) -> None:
    """`partial` es exactamente el máximo que se puede afirmar sin referencia."""
    capture_id = await _insert_capture(connection)
    extraction_id = await _insert_extraction(connection, capture_id)
    await connection.execute(
        sa.text(
            "INSERT INTO offer_requirements (extraction_id, position, text, "
            "source_quote, kind, category, match) VALUES "
            "(:e, 1, 'SQL', 'Imprescindible SQL', 'mandatory', 'technology', "
            "'partial')"
        ),
        {"e": extraction_id},
    )


async def test_two_requirements_cannot_share_a_position(
    connection: AsyncConnection,
) -> None:
    """El orden del anuncio se conserva, y no lo decide el planificador."""
    capture_id = await _insert_capture(connection)
    extraction_id = await _insert_extraction(connection, capture_id)
    insert = sa.text(
        "INSERT INTO offer_requirements (extraction_id, position, text, "
        "source_quote, kind, category) VALUES "
        "(:e, 1, 'SQL', 'Imprescindible SQL', 'mandatory', 'technology')"
    )
    await connection.execute(insert, {"e": extraction_id})
    with pytest.raises(IntegrityError, match="extraction_id_position"):
        await connection.execute(insert, {"e": extraction_id})


async def test_a_company_with_a_live_extraction_cannot_be_deleted(
    connection: AsyncConnection,
) -> None:
    """`RESTRICT` y no `CASCADE`: borrar una empresa no borra ofertas."""
    capture_id = await _insert_capture(connection)
    company_id = (
        await connection.execute(
            sa.text(
                "INSERT INTO companies (name, name_key) "
                "VALUES ('Astillero Nube SL', 'astillero nube sl') RETURNING id"
            )
        )
    ).scalar_one()
    await connection.execute(
        sa.text(
            "INSERT INTO offer_extractions (capture_id, prompt_version, model, "
            "evidence, posting_status, posting_company_id) "
            "VALUES (:c, 'test/0', 'stub', '{}', 'unverifiable', :company)"
        ),
        {"c": capture_id, "company": company_id},
    )
    with pytest.raises(IntegrityError, match="posting_company_id"):
        await connection.execute(
            sa.text("DELETE FROM companies WHERE id = :id"), {"id": company_id}
        )


# ---------------------------------------------------------------------------
# El mapeo de los modelos
# ---------------------------------------------------------------------------


async def test_the_orm_writes_and_reads_the_whole_shape(
    connection: AsyncConnection,
) -> None:
    """Un recorrido completo por el ORM: escribir, leer, y los tipos de vuelta.

    Comprueba que los valores de vocabulario vuelven como `StrEnum` y no
    como cadenas —que es lo que se perdería si alguna columna dejara de ser
    `sa.Enum`— y que las hijas se cargan sin pedirlo, porque la pantalla de
    la oferta las necesita siempre.
    """
    async with AsyncSession(bind=connection) as session:
        capture = OfferCapture(
            source=vocab.SourceChannel.PASTE,
            raw_text=ANUNCIO,
            raw_text_sha256="c" * 64,
        )
        extraction = OfferExtraction(
            capture=capture,
            prompt_version="test/0",
            model="stub",
            posting_status=vocab.PostingStatus.UNVERIFIABLE,
            title="Ingeniero de Datos",
            role_family=vocab.RoleFamily.DATA_ENGINEER,
            work_mode=vocab.WorkMode.HYBRID,
            hiring_regions=["ES"],
            responsibilities=["Mantener los pipelines de datos"],
            evidence={
                "title": {
                    "status": "published",
                    "source_quote": "busca Ingeniero de Datos",
                },
                "work_mode": {
                    "status": "published",
                    "source_quote": "Modalidad híbrida",
                },
                "comp_amount_min": {"status": "absent"},
            },
        )
        requirement = OfferRequirement(
            extraction=extraction,
            position=1,
            text="SQL",
            source_quote="Imprescindible SQL",
            kind=vocab.RequirementKind.MANDATORY,
            category=vocab.RequirementCategory.TECHNOLOGY,
        )
        extraction.anomalies.append(
            OfferAnomaly(
                requirement=requirement,
                position=1,
                text="tres años de experiencia con SQL para un puesto junior",
                explanation="anomalía inventada para el test",
                source_quote="tres años de experiencia",
            )
        )
        session.add(capture)
        await session.flush()
        capture_id = capture.id
        session.expunge_all()

        loaded = (
            await session.execute(
                sa.select(OfferExtraction).where(
                    OfferExtraction.capture_id == capture_id
                )
            )
        ).scalar_one()

    assert loaded.role_family is vocab.RoleFamily.DATA_ENGINEER
    assert loaded.work_mode is vocab.WorkMode.HYBRID
    assert loaded.posting_status is vocab.PostingStatus.UNVERIFIABLE
    # Sin `match` en M1: cruzar contra el banco de evidencias exige leer el
    # repositorio privado, y eso es M3. NULL es «sin evaluar», que no es lo
    # mismo que `no_evidence`.
    assert loaded.requirements[0].match is None
    assert loaded.anomalies[0].requirement_id == loaded.requirements[0].id
    assert loaded.evidence["comp_amount_min"] == {"status": "absent"}
    assert loaded.corrections == []
    assert loaded.extracted_at is not None
