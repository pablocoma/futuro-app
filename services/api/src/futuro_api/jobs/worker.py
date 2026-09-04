"""Punto de entrada del worker.

El worker comparte imagen con la api y solo cambia el comando:
`arq futuro_api.jobs.worker.WorkerSettings`. Nada de lo que necesita es
distinto —misma base de datos, misma configuración, mismo cliente de LLM—
salvo que no atiende HTTP.

Este fichero se importa al arrancar el worker y no desde la aplicación: leer
`WorkerSettings` construye la configuración, así que importarlo con un
entorno incompleto falla. Por eso la tarea vive en `tasks.py` y aquí solo
está el arranque.
"""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from futuro_api import db
from futuro_api.config import get_settings
from futuro_api.jobs.tasks import (
    MAX_ATTEMPTS,
    assess_offer,
    extract_offer,
    sweep_stale_runs,
)
from futuro_api.llm.factory import build_client

logger = logging.getLogger(__name__)

# Tiempo máximo de una tarea. Holgado sobre los dos minutos de espera del
# modelo por intento, para que un trabajo lento no se corte por la mitad
# dejando la fila en `running` y la extracción sin guardar.
JOB_TIMEOUT_SECONDS = 300

# Cada cuánto el worker escribe su latido en Redis. El valor por defecto de
# arq es una hora, que para un `healthcheck` de Compose no sirve de nada: el
# latido estaría rancio casi siempre y el contenedor se marcaría enfermo
# estando sano. Con quince segundos, `arq --check` dice la verdad.
HEALTH_CHECK_SECONDS = 15


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper())
    # arq trae su propio manejador para el logger `arq`, así que sin cortar
    # la propagación cada línea suya sale dos veces: la suya y la de la raíz
    # que acaba de configurar `basicConfig`.
    logging.getLogger("arq").propagate = False
    # `arq --watch` usa watchfiles, que en DEBUG escribe una línea cada vez
    # que no pasa nada. Con LOG_LEVEL=DEBUG en local, eso entierra los logs
    # que sí interesan.
    logging.getLogger("watchfiles").setLevel(logging.INFO)
    engine = db.create_engine(settings.database_url)
    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["sessions"] = db.create_session_factory(engine)
    ctx["llm"] = build_client(settings)
    logger.info(
        "worker arrancado (proveedor de LLM: %s, repositorio de datos: %s)",
        "simulado" if settings.llm_stubbed else settings.llm_provider,
        settings.data_repo_path or "sin configurar, no se podrá puntuar",
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [extract_offer, assess_offer]
    # Cada cinco minutos. Es un barrido de una sola sentencia UPDATE, así
    # que correrlo a menudo no cuesta nada y acorta el tiempo que un
    # trabajo perdido pasa aparentando estar en cola.
    cron_jobs = [
        cron(sweep_stale_runs, minute=set(range(0, 60, 5)), run_at_startup=True)
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = MAX_ATTEMPTS
    job_timeout = JOB_TIMEOUT_SECONDS
    health_check_interval = HEALTH_CHECK_SECONDS
