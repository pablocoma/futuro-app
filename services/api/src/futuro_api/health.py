"""Comprobación de salud.

Es público a propósito: lo consultan el healthcheck de Compose, Caddy y el
paso de verificación del deploy, ninguno de los cuales tiene sesión. No
expone nada que no sea el estado de los servicios.
"""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from futuro_api import data_repo, db
from futuro_api.config import Settings

router = APIRouter(prefix="/api", tags=["health"])


DataRepoStatus = Literal["ok", "unreadable", "not_configured"]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    version: str
    database: Literal["ok", "unreachable"]
    queue: Literal["ok", "unreachable"]
    # El repositorio de datos privado, de donde sale el modelo de scoring.
    # Se informa aparte y **no cuenta para el estado general**: ver el
    # comentario del endpoint.
    data_repo: DataRepoStatus
    data_repo_error: str | None = None


@router.get("/health")
async def health(request: Request, response: Response) -> Health:
    settings = cast(Settings, request.app.state.settings)
    engine = cast(AsyncEngine, request.app.state.engine)
    try:
        await db.ping(engine)
    except Exception:
        database: Literal["ok", "unreachable"] = "unreachable"
    else:
        database = "ok"

    # La cola se comprueba de verdad y no solo mirando si el objeto existe:
    # el pool se crea al arrancar y Redis puede haberse caído después.
    queue: Literal["ok", "unreachable"] = "unreachable"
    pool = getattr(request.app.state, "queue", None)
    if pool is not None:
        try:
            await pool.ping()
        except Exception:
            queue = "unreachable"
        else:
            queue = "ok"

    # El repositorio de datos se comprueba cargándolo, no mirando si el
    # directorio existe: lo que hace que el scoring funcione no es que haya
    # una carpeta, es que los seis YAML tengan la forma esperada. Es la
    # diferencia entre «no puntúa» y «no puntúa *por esto*».
    repo_status: DataRepoStatus = "not_configured"
    repo_error: str | None = None
    root = settings.data_repo_root
    if root is not None:
        try:
            data_repo.load(root)
        except data_repo.DataRepoError as error:
            repo_status = "unreadable"
            repo_error = str(error)
        else:
            repo_status = "ok"

    # El repositorio de datos **no** entra en el estado general, y es una
    # decisión: hasta que M3 traiga el clon no existe en la VM, y marcar el
    # contenedor como enfermo por eso lo reiniciaría en bucle. Lo único que
    # no funciona sin él es puntuar, y eso lo dice el trabajo que falla y
    # esta línea de aquí.
    healthy = database == "ok" and queue == "ok"
    overall: Literal["ok", "degraded"] = "ok" if healthy else "degraded"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Health(
        status=overall,
        env=settings.env,
        version=request.app.version,
        database=database,
        queue=queue,
        data_repo=repo_status,
        data_repo_error=repo_error,
    )
