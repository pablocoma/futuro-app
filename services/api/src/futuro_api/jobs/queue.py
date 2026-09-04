"""Encolar trabajos desde la API.

Separado de `worker.py` para que la API no importe el arranque del worker,
y de `tasks.py` para que los tests de la tarea no necesiten Redis.
"""

from __future__ import annotations

import logging
import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.config import Settings
from futuro_api.jobs import repository as jobs_repo
from futuro_api.jobs import vocabularies as vocab
from futuro_api.jobs.tasks import extract_offer
from futuro_api.models import JobRun

logger = logging.getLogger(__name__)


async def create_queue(settings: Settings) -> ArqRedis | None:
    """Abre el pool de la cola, o `None` si no hay cola configurada.

    Sin `REDIS_URL` no se intenta conectar. Es lo que permite levantar la
    aplicación sin cola —los tests que no la usan, o una consola de solo
    lectura— sin pagar los reintentos de conexión de una URL que no existe.
    Con `ENV=production` la variable es obligatoria.
    """
    if not settings.redis_url:
        return None
    redis = RedisSettings.from_dsn(settings.redis_url)
    # Un reintento y no los cinco de arq: el `depends_on` del compose espera
    # a que Redis esté sano antes de arrancar la API, así que si aquí falla
    # es que pasa algo de verdad, y alargar el arranque treinta segundos
    # solo retrasa el momento de enterarse.
    redis.conn_retries = 1
    return await create_pool(redis)


async def enqueue_extraction(
    queue: ArqRedis, session: AsyncSession, capture_id: uuid.UUID
) -> JobRun:
    """Crea la fila del trabajo y lo encola, en ese orden.

    El orden importa y no es el intuitivo. La fila se guarda y se commitea
    **antes** de encolar, porque el worker puede empezar a ejecutar el
    trabajo en el mismo instante en que se encola: si la fila no estuviera
    guardada todavía, la tarea no encontraría su propio `job_run`.

    El riesgo que deja este orden es el contrario: si el encolado falla
    después del commit, queda una fila en `queued` que nadie va a ejecutar.
    Eso lo recoge el barrido de trabajos estancados, que la marcará como
    perdida. Es el fallo que se prefiere: visible y recuperable, en lugar de
    un trabajo que se ejecuta contra una fila que no existe.
    """
    run = await jobs_repo.create_run(
        session, kind=vocab.JobKind.OFFER_EXTRACTION, capture_id=capture_id
    )
    await session.commit()

    job = await queue.enqueue_job(extract_offer.__name__, str(run.id))
    if job is not None:
        await jobs_repo.attach_arq_job_id(session, run.id, job.job_id)
        await session.commit()
    else:  # pragma: no cover - arq solo devuelve None con job_id repetido
        logger.warning("el trabajo %s no se encoló: ya había uno igual", run.id)
    return run
