"""Fixtures de la API.

Los tests no necesitan Postgres: `/api/health` degrada a `unreachable`
cuando la base no responde, y eso es precisamente uno de los casos que hay
que cubrir. El caso `ok` se cubre sustituyendo el ping.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from futuro_api.config import Settings
from futuro_api.main import create_app

ALLOWED = "allowed@example.test"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "env": "development",
        "session_secret": "test-secret",
        "google_client_id": "test-client-id",
        "google_client_secret": "test-client-secret",
        "allowed_emails": ALLOWED,
        "postgres_host": "127.0.0.1",
        "postgres_port": 1,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def make_app(**overrides: object) -> FastAPI:
    return create_app(make_settings(**overrides))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(make_app()) as test_client:
        yield test_client
