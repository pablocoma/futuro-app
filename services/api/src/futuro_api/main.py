"""Punto de entrada de la API.

Todo va bajo `/api` y detrás de Caddy en el mismo dominio que el frontend,
así que no hay CORS ni tokens en `localStorage`: solo la cookie de sesión
firmada.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from futuro_api import auth, db, health
from futuro_api.config import Settings, get_settings

VERSION = "0.1.0"

# Rutas accesibles sin sesión. El resto de `/api` exige usuario autenticado.
PUBLIC_PATHS = frozenset({"/api/health", "/api/openapi.json"})
PUBLIC_PREFIXES = ("/api/auth/", "/api/docs", "/api/redoc")


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = db.create_engine(settings.database_url)
        app.state.engine = engine
        app.state.sessions = db.create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="futuro-app API",
        version=VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.oauth = auth.build_oauth(settings)

    @app.middleware("http")
    async def require_session(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Cierra la API por defecto.

        Denegar salvo lista explícita, y no lo contrario: una ruta nueva de
        M1 queda protegida por omisión en lugar de quedar abierta porque
        alguien olvidó una dependencia.
        """
        if _is_public(request.url.path):
            return await call_next(request)
        if auth.current_user(request) is None:
            return JSONResponse({"detail": "no autenticado"}, status_code=401)
        return await call_next(request)

    # El orden importa y es contraintuitivo: Starlette ejecuta primero el
    # middleware añadido más tarde, así que SessionMiddleware se registra
    # DESPUÉS de la puerta para quedar por fuera. Al revés, `request.session`
    # no existiría todavía cuando la puerta lo consulta.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=settings.session_cookie_name,
        max_age=settings.session_max_age_seconds,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
