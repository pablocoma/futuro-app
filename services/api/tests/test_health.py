from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from futuro_api import db
from tests.conftest import make_app


def test_health_is_public_and_reports_env(client: TestClient) -> None:
    response = client.get("/api/health")
    body = response.json()
    assert body["env"] == "development"
    assert body["version"] == "0.1.0"


def test_health_degrades_when_database_is_unreachable(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "env": "development",
        "version": "0.1.0",
        "database": "unreachable",
    }


def test_health_is_ok_when_database_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ping(engine: object) -> None:
        return None

    monkeypatch.setattr(db, "ping", fake_ping)
    with TestClient(make_app()) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
