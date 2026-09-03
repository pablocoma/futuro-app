"""El rastro de qué se ejecutó, cuándo y a qué precio.

A diferencia de las capas del contrato, estas filas se actualizan: un
trabajo pasa por `queued`, `running` y su estado final. Por eso no llevan el
trigger de inmutabilidad.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.jobs import vocabularies as vocab
from futuro_api.llm import LlmResult
from futuro_api.models import JobRun, LlmCall

# Cuánto del mensaje de error se guarda. Suficiente para entender qué pasó
# —una extracción rechazada trae la lista entera de infracciones— y con
# tope, porque una excepción con un `repr` enorme no debe llenar la fila.
MAX_ERROR_CHARS = 2_000


def describe_error(error: BaseException) -> str:
    """Clase y mensaje. Nunca el texto del anuncio.

    Un fallo no es motivo para duplicar el anuncio en una columna de
    diagnóstico: para eso está `offer_captures.raw_text`, que es su sitio.
    """
    return f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS]


async def create_run(
    session: AsyncSession,
    *,
    kind: vocab.JobKind,
    capture_id: uuid.UUID | None = None,
) -> JobRun:
    run = JobRun(kind=kind, status=vocab.JobStatus.QUEUED, capture_id=capture_id)
    session.add(run)
    await session.flush()
    return run


async def attach_arq_job_id(
    session: AsyncSession, run_id: uuid.UUID, arq_job_id: str
) -> None:
    """Anota el identificador de la cola, para poder cruzar fila y trabajo."""
    await session.execute(
        sa.update(JobRun).where(JobRun.id == run_id).values(arq_job_id=arq_job_id)
    )


async def mark_running(
    session: AsyncSession, run_id: uuid.UUID, *, attempt: int
) -> None:
    await session.execute(
        sa.update(JobRun)
        .where(JobRun.id == run_id)
        .values(
            status=vocab.JobStatus.RUNNING,
            attempt=attempt,
            started_at=sa.func.now(),
            finished_at=None,
            error=None,
        )
    )


async def mark_succeeded(session: AsyncSession, run_id: uuid.UUID) -> None:
    await session.execute(
        sa.update(JobRun)
        .where(JobRun.id == run_id)
        .values(status=vocab.JobStatus.SUCCEEDED, finished_at=sa.func.now())
    )


async def mark_failed(session: AsyncSession, run_id: uuid.UUID, *, error: str) -> None:
    await session.execute(
        sa.update(JobRun)
        .where(JobRun.id == run_id)
        .values(status=vocab.JobStatus.FAILED, finished_at=sa.func.now(), error=error)
    )


async def mark_requeued(
    session: AsyncSession, run_id: uuid.UUID, *, error: str
) -> None:
    """Devuelve el trabajo a la cola tras un fallo que se va a reintentar.

    Se vuelve a `queued` en vez de dejarlo en `running`: mientras la cola
    espera para reintentar, nadie está ejecutando nada, y la pantalla debe
    decir «en cola» y no «en curso». Se reajusta `queued_at` para que el
    detector de trabajos estancados mida desde este reintento y no desde el
    primero.
    """
    await session.execute(
        sa.update(JobRun)
        .where(JobRun.id == run_id)
        .values(
            status=vocab.JobStatus.QUEUED,
            queued_at=sa.func.now(),
            started_at=None,
            error=error,
        )
    )


async def record_llm_call[T: BaseModel](
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    purpose: str,
    prompt_version: str,
    result: LlmResult[T],
) -> LlmCall:
    """Registra la llamada y su coste.

    Se guarda pase lo que pase después: si la validación rechaza la
    extracción, la llamada ya está pagada y el gasto tiene que constar.
    Registrar el coste solo de las extracciones que salen bien haría que el
    total mintiera justamente cuando el modelo se porta mal.

    `prompt_version` la trae quien llama y no viene en `LlmResult`, porque
    `llm/` no sabe qué es un prompt de extracción. Es la columna que permite
    comparar el coste de dos versiones del prompt sobre el mismo trabajo.
    """
    call = LlmCall(
        job_run_id=run_id,
        purpose=purpose,
        provider=result.provider,
        model=result.model,
        prompt_version=prompt_version,
        request_id=result.request_id,
        input_tokens=result.usage.input_tokens,
        cached_input_tokens=result.usage.cached_input_tokens,
        output_tokens=result.usage.output_tokens,
        reasoning_tokens=result.usage.reasoning_tokens,
        pricing_version=result.pricing_version,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        status=result.status,
    )
    session.add(call)
    await session.flush()
    return call


async def latest_run_for_capture(
    session: AsyncSession, capture_id: uuid.UUID
) -> JobRun | None:
    return (
        await session.execute(
            sa.select(JobRun)
            .where(JobRun.capture_id == capture_id)
            .order_by(JobRun.queued_at.desc(), JobRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def fail_stale_runs(
    session: AsyncSession, *, older_than: timedelta
) -> list[uuid.UUID]:
    """Marca como fallidos los trabajos que llevan demasiado sin acabar.

    Hace falta porque un trabajo puede desaparecer sin dejar rastro: si
    Redis se reinicia, la cola se vacía y la fila se queda en `queued` para
    siempre. Sin esto, la pantalla enseñaría «en cola» de por vida y nadie
    sabría que hay que reintentar.

    El umbral se mide desde el último encolado y es generoso a propósito: el
    tiempo de espera del modelo es de dos minutos por intento, así que nada
    legítimo se acerca.
    """
    cutoff = datetime.now(UTC) - older_than
    stale = (
        await session.execute(
            sa.update(JobRun)
            .where(
                JobRun.status.in_([vocab.JobStatus.QUEUED, vocab.JobStatus.RUNNING]),
                JobRun.queued_at < cutoff,
            )
            .values(
                status=vocab.JobStatus.FAILED,
                finished_at=sa.func.now(),
                error=(
                    "el trabajo se quedó sin terminar y se dio por perdido; "
                    "vuelve a lanzar la extracción"
                ),
            )
            .returning(JobRun.id)
        )
    ).scalars()
    return list(stale)
