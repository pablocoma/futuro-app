"""Los endpoints del estado de una candidatura, contra la base de datos real.

Aparte de `test_offers_api.py` a propósito: a diferencia del dossier o la
puntuación, cambiar de estado no depende de ninguna extracción ni del
repositorio de datos, así que estos tests no necesitan ni `_extract` ni
`api_with_data_repo` -solo una captura, con `api` a secas-. La única prueba
que cruza las dos cosas -confirmar una variante no mueve el estado- vive en
`test_offers_api.py`, junto al resto del dossier, porque ahí ya está montado
el repositorio de datos que hace falta para confirmar algo.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import FakeQueue, client_with_queue
from tests.synthetic import ADVERT


def _ingest(client: TestClient, text: str = ADVERT, **extra: Any) -> Any:
    return client.post("/api/offers/ingest", json={"raw_text": text, **extra})


def test_the_status_endpoint_is_closed_without_a_session() -> None:
    with client_with_queue(dev_auth_bypass=False) as (client, _):
        response = client.post(
            "/api/offers/00000000-0000-0000-0000-000000000000/status",
            json={"status": "preparing"},
        )
        assert response.status_code == 401


def test_a_fresh_offer_reports_research_everywhere(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """Sin ningún cambio de estado, la oferta se enseña en `research`."""
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]

    summary = next(o for o in client.get("/api/offers").json() if o["id"] == capture_id)
    assert summary["status"] == "research"

    detail = client.get(f"/api/offers/{capture_id}").json()
    assert detail["status"] == "research"
    assert detail["status_history"] == []


def test_changing_status_returns_the_new_event(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]

    response = client.post(
        f"/api/offers/{capture_id}/status", json={"status": "preparing"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "preparing"
    assert body["occurred_at"]


def test_changing_status_is_reflected_in_the_detail_and_the_list(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]
    client.post(f"/api/offers/{capture_id}/status", json={"status": "submitted"})

    detail = client.get(f"/api/offers/{capture_id}").json()
    assert detail["status"] == "submitted"

    summary = next(o for o in client.get("/api/offers").json() if o["id"] == capture_id)
    assert summary["status"] == "submitted"


def test_the_detail_carries_the_full_history_newest_first(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]
    client.post(f"/api/offers/{capture_id}/status", json={"status": "preparing"})
    client.post(f"/api/offers/{capture_id}/status", json={"status": "submitted"})

    history = client.get(f"/api/offers/{capture_id}").json()["status_history"]
    assert [event["status"] for event in history] == ["submitted", "preparing"]


def test_any_transition_is_accepted_with_no_order_enforced(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """De `research` directo a `closed`: se descartó sin preparar nada."""
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]

    response = client.post(
        f"/api/offers/{capture_id}/status", json={"status": "closed"}
    )
    assert response.status_code == 201
    assert client.get(f"/api/offers/{capture_id}").json()["status"] == "closed"


def test_an_unknown_status_value_is_a_422(api: tuple[TestClient, FakeQueue]) -> None:
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]
    response = client.post(
        f"/api/offers/{capture_id}/status", json={"status": "ghosted"}
    )
    assert response.status_code == 422


def test_changing_status_for_an_offer_that_does_not_exist_is_a_404(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api
    response = client.post(
        "/api/offers/00000000-0000-0000-0000-000000000000/status",
        json={"status": "preparing"},
    )
    assert response.status_code == 404
