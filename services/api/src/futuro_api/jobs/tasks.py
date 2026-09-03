"""Las tareas que corre el worker.

Una sola por ahora: extraer una oferta. Es el primer trabajo que justifica
la cola, porque una llamada al modelo tarda entre cinco y treinta segundos y
nadie debe esperar eso con una petición HTTP abierta.

El reparto con la cola: arq decide *cuándo* se reintenta, y esta tarea
decide *si* tiene sentido reintentar. Un rechazo del modelo o una extracción
que incumple el contrato darán lo mismo en el segundo intento, así que se
marcan fallidos y no se relanzan; un fallo de red sí se relanza.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api.jobs import repository as jobs_repo
from futuro_api.llm import LlmClient, LlmError, LlmRefusal
from futuro_api.models import JobRun, OfferCapture
from futuro_api.offers import extraction, prompt, rules
from futuro_api.offers import repository as offers_repo

logger = logging.getLogger(__name__)

# Intentos totales, contando el primero. Tres porque los fallos que merecen
# reintento son transitorios —un 429, un corte de red— y si tres seguidos
# fallan, el problema no se arregla esperando.
MAX_ATTEMPTS = 3

# Un trabajo que lleva esto sin acabar se da por perdido. Generoso frente a
# los dos minutos de espera del modelo por intento: lo que se busca cazar es
# un trabajo que se esfumó, no uno lento.
STALE_AFTER = timedelta(minutes=15)


class PermanentFailure(Exception):
    """Un fallo que reintentar no arregla."""


async def extract_offer(ctx: dict[str, Any], job_run_id: str) -> None:
    """Extrae una oferta ya capturada y guarda el resultado.

    Recibe el identificador de la fila de `job_runs` y no el de la captura,
    porque la fila se crea antes de encolar: así, si el encolado falla,
    queda el rastro de un trabajo que nunca arrancó en vez de nada.
    """
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    client: LlmClient = ctx["llm"]
    run_id = uuid.UUID(job_run_id)
    attempt = int(ctx.get("job_try", 1))

    async with sessions() as session:
        run = await session.get(JobRun, run_id)
        if run is None:
            # Puede pasar si alguien borró la captura mientras el trabajo
            # esperaba en la cola: la fila se fue en cascada. No es un error
            # que merezca reintento.
            logger.warning("el trabajo %s ya no existe; se ignora", run_id)
            return
        if run.capture_id is None:
            await jobs_repo.mark_failed(
                session, run_id, error="el trabajo no apunta a ninguna captura"
            )
            await session.commit()
            return
        capture_id = run.capture_id
        await jobs_repo.mark_running(session, run_id, attempt=attempt)
        await session.commit()

    try:
        await _run_extraction(sessions, client, run_id=run_id, capture_id=capture_id)
    except PermanentFailure as failure:
        async with sessions() as session:
            await jobs_repo.mark_failed(
                session, run_id, error=jobs_repo.describe_error(failure)
            )
            await session.commit()
        # No se relanza: arq reintentaría algo que va a fallar igual.
        logger.warning("extracción %s fallida sin reintento: %s", run_id, failure)
        return
    except Exception as error:
        async with sessions() as session:
            if attempt >= MAX_ATTEMPTS:
                await jobs_repo.mark_failed(
                    session, run_id, error=jobs_repo.describe_error(error)
                )
            else:
                await jobs_repo.mark_requeued(
                    session, run_id, error=jobs_repo.describe_error(error)
                )
            await session.commit()
        if attempt >= MAX_ATTEMPTS:
            logger.error("extracción %s agotó los intentos: %s", run_id, error)
            return
        # Se relanza para que arq lo reintente con su espera.
        raise

    async with sessions() as session:
        await jobs_repo.mark_succeeded(session, run_id)
        await session.commit()


async def _run_extraction(
    sessions: async_sessionmaker[AsyncSession],
    client: LlmClient,
    *,
    run_id: uuid.UUID,
    capture_id: uuid.UUID,
) -> None:
    """Llama al modelo, valida y guarda.

    La llamada se hace **fuera** de la transacción que guarda: una petición
    de treinta segundos con una transacción abierta bloquearía filas todo
    ese rato por nada.
    """
    async with sessions() as session:
        capture = await session.get(OfferCapture, capture_id)
        if capture is None:
            raise PermanentFailure(f"la captura {capture_id} ya no existe")
        raw_text = capture.raw_text

    try:
        result = await extraction.extract(client, raw_text)
    except LlmRefusal as refusal:
        # El modelo se negó. Reintentar da lo mismo, así que es permanente.
        raise PermanentFailure(str(refusal)) from refusal
    except LlmError:
        # Fallo de la llamada: sí merece reintento, así que sube tal cual.
        raise

    # El coste se registra antes de validar: la llamada ya está pagada, y si
    # la validación rechaza la extracción el gasto tiene que constar igual.
    async with sessions() as session:
        await jobs_repo.record_llm_call(
            session,
            run_id=run_id,
            purpose=extraction.PURPOSE,
            prompt_version=prompt.PROMPT_VERSION,
            result=result,
        )
        await session.commit()

    try:
        validated = rules.validate(result.parsed, raw_text)
    except rules.ExtractionRejected as rejected:
        raise PermanentFailure(str(rejected)) from rejected

    async with sessions() as session:
        await offers_repo.save_extraction(
            session,
            capture_id=capture_id,
            job_run_id=run_id,
            prompt_version=prompt.PROMPT_VERSION,
            model=result.model,
            validated=validated,
        )
        await session.commit()


async def sweep_stale_runs(ctx: dict[str, Any]) -> int:
    """Da por perdidos los trabajos que se quedaron a medias.

    Corre periódicamente porque un trabajo puede desaparecer sin dejar
    rastro: si Redis se reinicia, la cola se vacía y la fila se queda en
    `queued` para siempre. Sin esto, la pantalla diría «en cola» de por vida.
    """
    sessions: async_sessionmaker[AsyncSession] = ctx["sessions"]
    async with sessions() as session:
        lost = await jobs_repo.fail_stale_runs(session, older_than=STALE_AFTER)
        await session.commit()
    if lost:
        logger.warning("%d trabajos dados por perdidos", len(lost))
    return len(lost)
