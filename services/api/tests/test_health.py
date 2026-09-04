from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from futuro_api import db
from tests.conftest import DATA_REPO, client_with_queue


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
        # Sin `REDIS_URL` no hay cola que consultar, y eso también degrada:
        # la aplicación vive pero no puede aceptar una extracción nueva.
        "queue": "unreachable",
        # Sin repositorio de datos no se puede puntuar, pero eso **no**
        # degrada: hasta que M3 traiga el clon no existe en la VM, y marcar
        # el contenedor como enfermo por eso lo reiniciaría en bucle.
        "data_repo": "not_configured",
        "data_repo_error": None,
    }


def test_health_is_ok_when_database_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ping(engine: object) -> None:
        return None

    monkeypatch.setattr(db, "ping", fake_ping)
    with client_with_queue() as (client, _):
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["queue"] == "ok"


def test_health_reports_a_readable_data_repo() -> None:
    """Con repositorio de datos, `/api/health` lo dice."""
    with client_with_queue(data_repo_path=str(DATA_REPO)) as (client, _):
        body = client.get("/api/health").json()
    assert body["data_repo"] == "ok"
    assert body["data_repo_error"] is None


def test_health_explains_an_unreadable_data_repo() -> None:
    """Un directorio que no es el repositorio de datos se dice, y por qué.

    Es la diferencia entre «no puntúa» y «no puntúa *por esto*». Se
    comprueba cargándolo y no mirando si la carpeta existe, porque lo que
    hace funcionar el scoring no es que haya una carpeta.
    """
    with client_with_queue(data_repo_path="/no/existe/este/directorio") as (
        client,
        _,
    ):
        body = client.get("/api/health").json()
    assert body["data_repo"] == "unreadable"
    assert "no es un directorio" in (body["data_repo_error"] or "")


def test_an_unreadable_data_repo_does_not_degrade_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lo único que se cae sin repositorio de datos es puntuar.

    El resto de la aplicación sigue sirviendo, así que el estado general no
    puede depender de esto. Si lo hiciera, el healthcheck de Compose
    reiniciaría el contenedor en bucle hasta que existiera el clon de M3.
    """

    async def fake_ping(engine: object) -> None:
        return None

    monkeypatch.setattr(db, "ping", fake_ping)
    with client_with_queue(data_repo_path="/no/existe") as (client, _):
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["data_repo"] == "unreadable"
