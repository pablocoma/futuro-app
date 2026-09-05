"""Tests de la puerta de entrada.

Lo que se comprueba aquí es lo que hace falta que sea cierto para que la
allowlist de un email sirva de algo: que la API esté cerrada por omisión,
que el bypass no exista en producción, y que un email fuera de la lista no
pueda quedarse dentro por tener una cookie vieja.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner
from pydantic import ValidationError

from futuro_api.auth import SESSION_USER_KEY
from tests.conftest import (
    ALLOWED,
    make_app,
    make_production_settings,
    make_settings,
)


def test_api_is_closed_by_default(client: TestClient) -> None:
    assert client.get("/api/me-no-existe").status_code == 401


def test_me_requires_a_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_dev_bypass_injects_a_fixed_user() -> None:
    with TestClient(
        make_app(dev_auth_bypass=True, dev_auth_email="dev@localhost")
    ) as client:
        body = client.get("/api/auth/me").json()
    assert body == {"email": "dev@localhost", "via": "dev-bypass"}


def test_dev_bypass_is_ignored_in_production() -> None:
    settings = make_production_settings(dev_auth_bypass=True)
    assert settings.dev_auth_bypass is True
    assert settings.bypass_active is False


def test_production_requires_oauth_credentials() -> None:
    with pytest.raises(ValidationError, match="GOOGLE_CLIENT_ID"):
        make_production_settings(google_client_id="")


def test_production_rejects_the_development_session_secret() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        make_production_settings(session_secret="dev-only-insecure-session-secret")


def test_production_requires_https_base_url() -> None:
    with pytest.raises(ValidationError, match="PUBLIC_BASE_URL"):
        make_production_settings(public_base_url="http://example.test")


def test_production_requires_the_data_repo() -> None:
    """Desde M3 el clon de solo lectura existe, y no arrancar sin él es la
    misma disciplina que ya aplican OAuth, el secreto de sesión y HTTPS: un
    esqueleto que levanta sin poder puntuar ni servir un PDF es peor que uno
    que no levanta.
    """
    with pytest.raises(ValidationError, match="DATA_REPO_PATH"):
        make_production_settings(data_repo_path="")


def test_cookie_is_secure_only_in_production() -> None:
    assert make_settings().cookie_secure is False
    assert make_production_settings().cookie_secure is True


def test_allowlist_is_parsed_case_insensitively() -> None:
    settings = make_settings(allowed_emails=" A@Example.test , b@example.test ")
    assert settings.allowed_email_set == frozenset(["a@example.test", "b@example.test"])


def test_a_signed_session_for_an_allowed_email_is_accepted() -> None:
    with TestClient(make_app()) as client:
        client.cookies.set("futuro_session", sign_session(ALLOWED))
        response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json() == {"email": ALLOWED, "via": "google"}


def test_session_of_an_email_removed_from_the_allowlist_stops_working() -> None:
    """Quitar un email de ALLOWED_EMAILS cierra su sesión al instante.

    La cookie sigue estando bien firmada y sin caducar: lo que la invalida
    es que la allowlist se revalida en cada petición.
    """
    with TestClient(make_app(allowed_emails="otro@example.test")) as client:
        client.cookies.set("futuro_session", sign_session(ALLOWED))
        assert client.get("/api/auth/me").status_code == 401


def sign_session(email: str) -> str:
    """Cookie de sesión de Starlette firmada con la clave de los tests."""
    payload = base64.b64encode(json.dumps({SESSION_USER_KEY: email}).encode())
    return TimestampSigner("test-secret").sign(payload).decode()
