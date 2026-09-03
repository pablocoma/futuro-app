"""OAuth de Google con allowlist de un email.

Reparto de responsabilidad: Authlib habla con Google y valida el `id_token`;
este módulo decide si el email resultante tiene permiso y firma la cookie de
sesión. La allowlist se comprueba **después** de verificar el token, nunca
sobre un email que venga del cliente.
"""

from __future__ import annotations

from typing import Any, cast

from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from futuro_api.config import Settings, get_settings

GOOGLE_METADATA_URL = "https://accounts.google.com/.well-known/openid-configuration"

SESSION_USER_KEY = "user_email"

router = APIRouter(prefix="/api/auth", tags=["auth"])


class CurrentUser(BaseModel):
    email: str
    via: str


def build_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=GOOGLE_METADATA_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth


def _google_client(request: Request) -> StarletteOAuth2App:
    oauth = cast(OAuth, request.app.state.oauth)
    return cast(StarletteOAuth2App, oauth.create_client("google"))


def current_user(request: Request) -> CurrentUser | None:
    """El usuario de la petición, o `None` si no hay sesión válida.

    En desarrollo con `DEV_AUTH_BYPASS=true` devuelve un usuario fijo sin
    tocar Google. `Settings.bypass_active` ya garantiza que eso solo puede
    ocurrir con `ENV=development`.
    """
    settings = cast(Settings, request.app.state.settings)
    if settings.bypass_active:
        return CurrentUser(email=settings.dev_auth_email, via="dev-bypass")
    email = request.session.get(SESSION_USER_KEY)
    if not isinstance(email, str) or not email:
        return None
    # Revalidar contra la allowlist en cada petición: quitar un email de
    # ALLOWED_EMAILS debe cerrar la sesión al instante, no al caducar.
    if email.lower() not in settings.allowed_email_set:
        return None
    return CurrentUser(email=email, via="google")


def require_user(request: Request) -> CurrentUser:
    user = current_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="no autenticado"
        )
    return user


@router.get("/login")
async def login(request: Request) -> Any:
    settings = cast(Settings, request.app.state.settings)
    if settings.bypass_active:
        return RedirectResponse(url="/")
    redirect_uri = f"{settings.public_base_url.rstrip('/')}/api/auth/callback"
    return await _google_client(request).authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    settings = cast(Settings, request.app.state.settings)
    client = _google_client(request)
    token = await client.authorize_access_token(request)
    claims = token.get("userinfo") or {}
    email = str(claims.get("email") or "")
    verified = bool(claims.get("email_verified"))
    if not email or not verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Google no devolvió un email verificado",
        )
    if email.lower() not in settings.allowed_email_set:
        # Sin detalle de por qué: no se confirma a un tercero qué emails
        # están en la allowlist.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="cuenta no autorizada"
        )
    request.session.clear()
    request.session[SESSION_USER_KEY] = email
    return RedirectResponse(url="/")


@router.post("/logout")
async def logout(request: Request) -> dict[str, bool]:
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(request: Request) -> CurrentUser:
    return require_user(request)


__all__ = [
    "CurrentUser",
    "build_oauth",
    "current_user",
    "require_user",
    "router",
    "get_settings",
]
