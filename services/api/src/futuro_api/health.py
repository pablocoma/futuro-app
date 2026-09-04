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

from futuro_api import db
from futuro_api.config import Settings

router = APIRouter(prefix="/api", tags=["health"])


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    env: str
    version: str
    database: Literal["ok", "unreachable"]
    queue: Literal["ok", "unreachable"]


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
    )
