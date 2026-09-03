"""La tarea del worker: qué guarda, qué reintenta y qué no.

Se prueba contra Postgres de verdad y con la fábrica de sesiones real, no
dentro de una transacción que se deshace: la tarea commitea varias veces a
propósito —el coste de la llamada se guarda aparte de la extracción— y esa
estructura es parte de lo que interesa comprobar.

Redis no aparece: la tarea se invoca directamente. Lo que arq aporta es
*cuándo* se reintenta, y eso no se prueba probando arq.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api.jobs import repository as jobs_repo
from futuro_api.jobs import tasks
from futuro_api.jobs import vocabularies as jobs_vocab
from futuro_api.llm import LlmError, LlmRefusal, LlmResult
from futuro_api.llm.stub import StubClient
from futuro_api.models import JobRun, LlmCall, OfferCapture, OfferExtraction
from futuro_api.offers import extraction, prompt, schemas
from futuro_api.offers import repository as offers_repo
from futuro_api.offers import vocabularies as vocab
from tests.synthetic import ADVERT, absent, good_draft


class _ExplodingClient:
    """Un cliente que solo sabe fallar, para probar los dos caminos."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def structured[T: BaseModel](
        self, *, purpose: str, system: str, user: str, schema: type[T]
    ) -> LlmResult[T]:
        raise self._error


def _rule_breaking_draft(_: str) -> schemas.ExtractionDraft:
    """Una respuesta que rellena un campo declarado como ausente.

    Es la infracción que no admite degradación: si el dato no está en el
    anuncio, el valor no puede venir de ninguna parte legítima.
    """
    draft = good_draft()
    draft.compensation.equity = absent()
    draft.compensation.equity.value = "0,5% en opciones a cuatro años"
    return draft


def _stub(builder: Any = extraction.canned_draft) -> StubClient:
    return StubClient({extraction.PURPOSE: builder})


async def _prepare(
    sessions: async_sessionmaker[AsyncSession], text: str = ADVERT
) -> tuple[uuid.UUID, uuid.UUID]:
    """Deja una captura y su trabajo en cola, como haría el endpoint."""
    async with sessions() as session:
        capture = await offers_repo.create_capture(
            session, source=vocab.SourceChannel.PASTE, raw_text=text
        )
        run = await jobs_repo.create_run(
            session,
            kind=jobs_vocab.JobKind.OFFER_EXTRACTION,
            capture_id=capture.id,
        )
        await session.commit()
        return capture.id, run.id


def _context(
    sessions: async_sessionmaker[AsyncSession], client: Any, attempt: int = 1
) -> dict[str, Any]:
    return {"sessions": sessions, "llm": client, "job_try": attempt}


async def _run(session: AsyncSession, run_id: uuid.UUID) -> JobRun:
    run = await session.get(JobRun, run_id)
    assert run is not None
    return run


# ---------------------------------------------------------------------------
# El camino bueno
# ---------------------------------------------------------------------------


async def test_a_successful_extraction_is_saved_and_the_run_succeeds(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    capture_id, run_id = await _prepare(sessions)

    await tasks.extract_offer(_context(sessions, _stub()), str(run_id))

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.SUCCEEDED
        assert run.error is None
        assert run.started_at is not None and run.finished_at is not None
        assert run.attempt == 1

        saved = await offers_repo.current_extraction(session, capture_id)
        assert saved is not None
        assert saved.job_run_id == run_id
        assert saved.prompt_version == prompt.PROMPT_VERSION
        assert saved.model == "stub"
        assert saved.title is not None


async def test_the_call_is_recorded_with_its_cost_and_prompt_version(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await _prepare(sessions)

    await tasks.extract_offer(_context(sessions, _stub()), str(run_id))

    async with sessions() as session:
        call = (
            await session.execute(
                sa.select(LlmCall).where(LlmCall.job_run_id == run_id)
            )
        ).scalar_one()
        assert call.purpose == extraction.PURPOSE
        assert call.prompt_version == prompt.PROMPT_VERSION
        assert call.cost_usd == Decimal(0)
        assert call.model == "stub"
        assert call.status is jobs_vocab.LlmCallStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# Fallos que no se reintentan
# ---------------------------------------------------------------------------


async def test_a_rejected_extraction_fails_without_saving_anything(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Mejor sin extracción que con una que miente."""
    _, run_id = await _prepare(sessions)

    await tasks.extract_offer(
        _context(sessions, _stub(_rule_breaking_draft)), str(run_id)
    )

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.FAILED
        assert run.error is not None
        assert "absent" in run.error
        total = (
            await session.execute(
                sa.select(sa.func.count()).select_from(OfferExtraction)
            )
        ).scalar_one()
        assert total == 0


async def test_a_rejected_extraction_still_records_what_the_call_cost(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """La llamada ya está pagada, así que el gasto tiene que constar.

    Registrar el coste solo de las extracciones que salen bien haría que el
    total mintiera justamente cuando el modelo se porta mal.
    """
    _, run_id = await _prepare(sessions)

    await tasks.extract_offer(
        _context(sessions, _stub(_rule_breaking_draft)), str(run_id)
    )

    async with sessions() as session:
        calls = (
            (
                await session.execute(
                    sa.select(LlmCall).where(LlmCall.job_run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(calls) == 1


async def test_a_refusal_fails_without_retrying(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Reintentar una negativa del modelo da lo mismo, así que no se relanza."""
    _, run_id = await _prepare(sessions)
    client = _ExplodingClient(LlmRefusal("no puedo ayudarte con esto"))

    # No lanza: si lanzara, arq lo reintentaría tres veces para nada.
    await tasks.extract_offer(_context(sessions, client), str(run_id))

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.FAILED
        assert run.error is not None and "no puedo ayudarte" in run.error


async def test_a_run_whose_capture_vanished_fails_without_retrying(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    capture_id, run_id = await _prepare(sessions)
    async with sessions() as session:
        await session.execute(
            sa.delete(OfferCapture).where(OfferCapture.id == capture_id)
        )
        await session.commit()

    # La captura se fue y con ella su trabajo, en cascada: la tarea no
    # encuentra la fila y no hay nada que hacer.
    await tasks.extract_offer(_context(sessions, _stub()), str(run_id))

    async with sessions() as session:
        assert await session.get(JobRun, run_id) is None


async def test_a_job_that_no_longer_exists_is_ignored(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await tasks.extract_offer(_context(sessions, _stub()), str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Fallos que sí se reintentan
# ---------------------------------------------------------------------------


async def test_a_transient_failure_goes_back_to_the_queue_and_is_reraised(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Vuelve a `queued` y no se queda en `running`.

    Mientras la cola espera para reintentar, nadie está ejecutando nada, y
    la pantalla debe decir «en cola» y no «en curso».
    """
    _, run_id = await _prepare(sessions)
    client = _ExplodingClient(LlmError("la conexión se cortó"))

    with pytest.raises(LlmError):
        await tasks.extract_offer(_context(sessions, client, attempt=1), str(run_id))

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.QUEUED
        assert run.started_at is None
        assert run.error is not None and "se cortó" in run.error


async def test_the_last_attempt_fails_for_good_and_does_not_reraise(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await _prepare(sessions)
    client = _ExplodingClient(LlmError("la conexión se cortó otra vez"))

    await tasks.extract_offer(
        _context(sessions, client, attempt=tasks.MAX_ATTEMPTS), str(run_id)
    )

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.FAILED
        assert run.attempt == tasks.MAX_ATTEMPTS


# ---------------------------------------------------------------------------
# Trabajos perdidos
# ---------------------------------------------------------------------------


async def test_a_job_that_vanished_is_eventually_given_up_on(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Si Redis se reinicia, la cola se vacía y la fila se queda en `queued`.

    Sin este barrido, la pantalla enseñaría «en cola» de por vida y nadie
    sabría que hay que reintentar.
    """
    _, forgotten = await _prepare(sessions)
    _, recent = await _prepare(sessions, "Otro anuncio inventado, más reciente.")
    async with sessions() as session:
        await session.execute(
            sa.update(JobRun)
            .where(JobRun.id == forgotten)
            .values(
                queued_at=datetime.now(UTC) - tasks.STALE_AFTER - timedelta(minutes=1)
            )
        )
        await session.commit()

    lost = await tasks.sweep_stale_runs({"sessions": sessions})

    assert lost == 1
    async with sessions() as session:
        assert (await _run(session, forgotten)).status is jobs_vocab.JobStatus.FAILED
        assert (await _run(session, recent)).status is jobs_vocab.JobStatus.QUEUED


async def test_the_sweep_leaves_finished_runs_alone(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await _prepare(sessions)
    await tasks.extract_offer(_context(sessions, _stub()), str(run_id))
    async with sessions() as session:
        await session.execute(
            sa.update(JobRun)
            .where(JobRun.id == run_id)
            .values(
                queued_at=datetime.now(UTC) - tasks.STALE_AFTER - timedelta(hours=1)
            )
        )
        await session.commit()

    assert await tasks.sweep_stale_runs({"sessions": sessions}) == 0
    async with sessions() as session:
        assert (await _run(session, run_id)).status is jobs_vocab.JobStatus.SUCCEEDED
