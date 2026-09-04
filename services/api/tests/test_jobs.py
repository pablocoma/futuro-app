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
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api.assessment import calls as assessment_calls
from futuro_api.assessment import prompt as assessment_prompt
from futuro_api.assessment import repository as assessment_repo
from futuro_api.assessment import vocabularies as assessment_vocab
from futuro_api.jobs import repository as jobs_repo
from futuro_api.jobs import tasks, worker
from futuro_api.jobs import vocabularies as jobs_vocab
from futuro_api.llm import LlmError, LlmRefusal, LlmResult
from futuro_api.llm.stub import StubClient
from futuro_api.models import JobRun, LlmCall, OfferCapture, OfferExtraction
from futuro_api.offers import extraction, prompt, schemas
from futuro_api.offers import repository as offers_repo
from futuro_api.offers import vocabularies as vocab
from tests.conftest import DATA_REPO, make_settings
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


# ---------------------------------------------------------------------------
# El segundo tipo de trabajo: puntuar
# ---------------------------------------------------------------------------
# Es el que valida el diseño de M1: hace **dos** llamadas al modelo, que es
# lo que justificó que `job_runs` y `llm_calls` fueran dos tablas.


def test_every_job_kind_maps_to_a_task_that_exists() -> None:
    """El mapa `TASK_OF` tiene que seguir siendo el nombre real.

    arq registra cada tarea por su `__name__`, así que renombrar una
    función sin tocar el mapa encolaría un trabajo que nadie sabe ejecutar,
    y el síntoma sería una fila en `queued` para siempre. El mapa existe
    porque `queue.py` necesita el nombre y `tasks.py` necesita encolar
    —la extracción encadena la puntuación—, así que importarse mutuamente
    daba un ciclo.
    """
    registered = {function.__name__ for function in worker.WorkerSettings.functions}
    for kind in jobs_vocab.JobKind:
        assert kind in jobs_vocab.TASK_OF, f"«{kind.value}» no tiene tarea asignada"
        assert jobs_vocab.TASK_OF[kind] in registered, (
            f"la tarea de «{kind.value}» no está registrada en el worker"
        )


def _assessment_stub() -> StubClient:
    return StubClient(
        {
            extraction.PURPOSE: extraction.canned_draft,
            assessment_calls.SCORING_PURPOSE: assessment_calls.canned_scoring,
            assessment_calls.VARIANT_PURPOSE: assessment_calls.canned_variant,
        }
    )


def _assessment_context(
    sessions: async_sessionmaker[AsyncSession],
    *,
    data_repo_path: str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    return {
        "sessions": sessions,
        "llm": client or _assessment_stub(),
        "settings": make_settings(
            data_repo_path=(
                str(DATA_REPO) if data_repo_path is None else data_repo_path
            )
        ),
        "job_try": 1,
    }


async def _extracted(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Una oferta extraída y un trabajo de puntuación en cola."""
    capture_id, extract_run = await _prepare(sessions)
    await tasks.extract_offer(_assessment_context(sessions), str(extract_run))
    async with sessions() as session:
        run = await jobs_repo.create_run(
            session,
            kind=jobs_vocab.JobKind.OFFER_ASSESSMENT,
            capture_id=capture_id,
        )
        await session.commit()
        return capture_id, run.id


async def test_a_successful_assessment_saves_the_score_and_the_variant(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    capture_id, run_id = await _extracted(sessions)

    await tasks.assess_offer(_assessment_context(sessions), str(run_id))

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.SUCCEEDED
        saved = await offers_repo.current_extraction(session, capture_id)
        assert saved is not None
        assessment = await assessment_repo.current_assessment(session, saved.id)
        assert assessment is not None
        assert assessment.job_run_id == run_id
        assert assessment.source is assessment_vocab.AssessmentSource.LLM
        assert assessment.prompt_version == assessment_prompt.SCORING_PROMPT_VERSION
        # La versión **y** el hash del modelo de scoring: `version: 1` no
        # cambió las dos veces que el modelo cambió el 2026-08-13.
        assert assessment.scoring_model_version == "7"
        assert len(assessment.scoring_model_sha256) == 64
        variant = await assessment_repo.current_variant_recommendation(
            session, saved.id
        )
        assert variant is not None
        assert variant.job_run_id == run_id
        assert len(variant.variants_guide_sha256) == 64


async def test_one_assessment_job_makes_two_calls_with_distinct_purposes(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Lo que justificó separar `job_runs` de `llm_calls` en M1.

    Dos propósitos y no uno: es lo que permite mirar cuánto cuesta puntuar y
    cuánto cuesta elegir variante por separado, en vez de un total ciego.
    """
    _, run_id = await _extracted(sessions)

    await tasks.assess_offer(_assessment_context(sessions), str(run_id))

    async with sessions() as session:
        purposes = (
            (
                await session.execute(
                    sa.select(LlmCall.purpose).where(LlmCall.job_run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
    assert set(purposes) == {
        assessment_calls.SCORING_PURPOSE,
        assessment_calls.VARIANT_PURPOSE,
    }


async def test_a_missing_data_repo_fails_without_retrying(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Y falla **antes** de llamar al modelo.

    Descubrirlo después de pagar dos llamadas sería tirar el dinero por una
    comprobación que cuesta leer seis ficheros. Reintentar tampoco arregla
    un directorio que no está.
    """
    _, run_id = await _extracted(sessions)

    await tasks.assess_offer(
        _assessment_context(sessions, data_repo_path=""), str(run_id)
    )

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.FAILED
        assert "DATA_REPO_PATH" in (run.error or "")
        assert (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(LlmCall)
                .where(LlmCall.job_run_id == run_id)
            )
        ).scalar_one() == 0


async def test_an_unreadable_data_repo_fails_without_retrying(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, run_id = await _extracted(sessions)

    await tasks.assess_offer(
        _assessment_context(sessions, data_repo_path="/no/existe"), str(run_id)
    )

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.FAILED
        assert "no es un directorio" in (run.error or "")


async def test_an_offer_without_an_extraction_cannot_be_scored(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Sin extracción vigente no hay nada que puntuar, y no se reintenta."""
    capture_id, _ = await _prepare(sessions)
    async with sessions() as session:
        run = await jobs_repo.create_run(
            session,
            kind=jobs_vocab.JobKind.OFFER_ASSESSMENT,
            capture_id=capture_id,
        )
        await session.commit()
        run_id = run.id

    await tasks.assess_offer(_assessment_context(sessions), str(run_id))

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.FAILED
        assert "extracción vigente" in (run.error or "")


def _bad_variant(user_prompt: str) -> Any:
    """Una elección de variante que no existe."""
    draft = assessment_calls.canned_variant(user_prompt)
    draft.variant = "variante_que_no_existe"
    return draft


async def test_a_rejected_variant_saves_nothing_at_all(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """El trabajo es atómico: si la variante no se sostiene, no hay assessment.

    Guardar medio resultado dejaría una oferta puntuada y sin variante que
    nadie distinguiría de una a la que todavía le falta la variante, y el
    trabajo aparecería como fallido habiendo escrito algo. Cuesta las dos
    llamadas, que es el mismo precio que M1 aceptó al rechazar una
    extracción entera.
    """
    capture_id, run_id = await _extracted(sessions)
    client = StubClient(
        {
            assessment_calls.SCORING_PURPOSE: assessment_calls.canned_scoring,
            assessment_calls.VARIANT_PURPOSE: _bad_variant,
        }
    )

    await tasks.assess_offer(_assessment_context(sessions, client=client), str(run_id))

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.FAILED
        assert "variante_que_no_existe" in (run.error or "")
        saved = await offers_repo.current_extraction(session, capture_id)
        assert saved is not None
        assert await assessment_repo.current_assessment(session, saved.id) is None
        # Y el coste de las dos llamadas consta igual: ya están pagadas.
        assert (
            await session.execute(
                sa.select(sa.func.count())
                .select_from(LlmCall)
                .where(LlmCall.job_run_id == run_id)
            )
        ).scalar_one() == 2


# ---------------------------------------------------------------------------
# El encadenado
# ---------------------------------------------------------------------------


class _RecordingQueue:
    """Una cola que apunta lo que se le encola, para ver el encadenado."""

    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue_job(self, function: str, *args: object) -> Any:
        self.enqueued.append(function)
        return SimpleNamespace(job_id=f"encadenado-{len(self.enqueued)}")


async def test_a_finished_extraction_chains_the_assessment(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Para que el recorrido siga siendo de punta a punta sin botón intermedio."""
    capture_id, run_id = await _prepare(sessions)
    queue = _RecordingQueue()
    context = _assessment_context(sessions)
    context["redis"] = queue

    await tasks.extract_offer(context, str(run_id))

    assert queue.enqueued == [jobs_vocab.TASK_OF[jobs_vocab.JobKind.OFFER_ASSESSMENT]]
    async with sessions() as session:
        runs = (
            (
                await session.execute(
                    sa.select(JobRun.kind).where(JobRun.capture_id == capture_id)
                )
            )
            .scalars()
            .all()
        )
    assert jobs_vocab.JobKind.OFFER_ASSESSMENT in runs


class _BrokenQueue:
    async def enqueue_job(self, function: str, *args: object) -> Any:
        raise ConnectionError("redis de mentira, caído a propósito")


async def test_a_failed_chaining_does_not_lose_the_extraction(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Perder una llamada ya pagada por no poder encolar la siguiente, no.

    La oferta se queda sin puntuar, la pantalla lo dice y el botón de
    puntuar sigue ahí.
    """
    capture_id, run_id = await _prepare(sessions)
    context = _assessment_context(sessions)
    context["redis"] = _BrokenQueue()

    await tasks.extract_offer(context, str(run_id))

    async with sessions() as session:
        run = await _run(session, run_id)
        assert run.status is jobs_vocab.JobStatus.SUCCEEDED
        assert await offers_repo.current_extraction(session, capture_id) is not None
