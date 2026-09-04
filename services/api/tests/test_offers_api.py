"""Los endpoints de ofertas, contra la base de datos de verdad.

La cola sí es de mentira: lo que hay que comprobar es *que* se encola un
trabajo y con qué argumentos, no que arq sepa hablar con Redis.

Todos los anuncios son inventados.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api.jobs import tasks
from futuro_api.jobs.tasks import extract_offer
from futuro_api.llm.stub import StubClient
from futuro_api.offers import extraction, schemas
from futuro_api.offers import repository as offers_repo
from futuro_api.offers import vocabularies as vocab
from tests.conftest import FakeQueue, client_with_queue
from tests.synthetic import ADVERT, absent, good_draft, published

OTRO_ANUNCIO = (
    "Cooperativa del Valle busca Analista de Datos para el almacén de Teruel. "
    "Trabajarás con el equipo de logística en los cuadros de mando de la "
    "cadena de frío. Imprescindible SQL y hojas de cálculo. Se valora "
    "experiencia con herramientas de visualización. Carné de conducir B. "
    "Jornada completa y contrato indefinido, con dos días de teletrabajo."
)


def _ingest(client: TestClient, text: str = ADVERT, **extra: Any) -> Any:
    return client.post("/api/offers/ingest", json={"raw_text": text, **extra})


# ---------------------------------------------------------------------------
# La puerta
# ---------------------------------------------------------------------------


def test_the_offer_endpoints_are_closed_without_a_session() -> None:
    """La API está cerrada por omisión y estas rutas no son una excepción.

    Se comprueba con el bypass de desarrollo apagado, que es lo que deja la
    aplicación sin usuario.
    """
    with client_with_queue(dev_auth_bypass=False) as (client, _):
        assert (
            client.post("/api/offers/ingest", json={"raw_text": ADVERT}).status_code
            == 401
        )
        assert client.get("/api/offers").status_code == 401


# ---------------------------------------------------------------------------
# Ingesta
# ---------------------------------------------------------------------------


def test_pasting_an_advert_captures_it_and_queues_the_extraction(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, queue = api
    response = _ingest(client)

    assert response.status_code == 202
    body = response.json()
    assert body["duplicate"] is False
    assert body["extraction_status"] == "queued"
    assert body["extraction_id"] is None
    assert len(body["raw_text_sha256"]) == 64

    # Se encola la tarea con el identificador del trabajo, no con el de la
    # captura: la fila existe antes de encolar, y es lo que la tarea busca.
    assert queue.enqueued == [(extract_offer.__name__, (body["job_run_id"],))]


def test_pasting_the_same_advert_twice_does_not_pay_twice(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """Devuelve la captura que ya había y no encola nada."""
    client, queue = api
    first = _ingest(client).json()
    response = _ingest(client)

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is True
    assert body["capture_id"] == first["capture_id"]
    assert body["job_run_id"] is None
    assert len(queue.enqueued) == 1


def test_the_same_advert_can_be_reextracted_on_purpose(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, queue = api
    first = _ingest(client).json()
    response = _ingest(client, force_reextract=True)

    assert response.status_code == 202
    body = response.json()
    assert body["capture_id"] == first["capture_id"]
    assert body["duplicate"] is True
    assert len(queue.enqueued) == 2


def test_a_text_too_short_to_be_an_advert_is_refused(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """Por debajo del mínimo el modelo devolvería `absent` en todo."""
    client, queue = api
    assert _ingest(client, "Buscamos ingeniero.").status_code == 422
    assert queue.enqueued == []


def test_the_other_four_channels_are_refused_explicitly(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """URL, extensión, Telegram y correo son Fase 4.

    Un 422 documentado en el OpenAPI, y no una aceptación silenciosa de algo
    que no hay código para procesar.
    """
    client, _ = api
    response = client.post(
        "/api/offers/ingest", json={"source": "url", "raw_text": ADVERT}
    )
    assert response.status_code == 422


def test_without_a_queue_the_ingest_says_so(api: tuple[TestClient, FakeQueue]) -> None:
    """La API vive sin Redis; lo único que no puede es aceptar trabajo."""
    client, _ = api
    client.app.state.queue = None  # type: ignore[attr-defined]
    response = _ingest(client)
    assert response.status_code == 503
    assert "cola" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Detalle
# ---------------------------------------------------------------------------


def test_an_offer_that_does_not_exist_is_a_404(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api
    missing = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/api/offers/{missing}").status_code == 404
    assert client.post(f"/api/offers/{missing}/reextract").status_code == 404


def test_a_captured_offer_shows_up_before_being_extracted(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """La pantalla tiene algo que enseñar mientras el worker trabaja."""
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]

    body = client.get(f"/api/offers/{capture_id}").json()
    assert body["extraction_status"] == "queued"
    assert body["extraction"] is None
    assert body["versions"] == []
    assert body["capture"]["source"] == "paste"
    assert body["capture"]["raw_text"] == ADVERT


def test_reextracting_queues_another_run(api: tuple[TestClient, FakeQueue]) -> None:
    client, queue = api
    capture_id = _ingest(client).json()["capture_id"]

    response = client.post(f"/api/offers/{capture_id}/reextract")
    assert response.status_code == 202
    assert len(queue.enqueued) == 2


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------


def test_offers_are_listed_newest_first(api: tuple[TestClient, FakeQueue]) -> None:
    client, _ = api
    first = _ingest(client).json()["capture_id"]
    second = _ingest(client, OTRO_ANUNCIO).json()["capture_id"]

    listed = client.get("/api/offers").json()
    assert [offer["id"] for offer in listed] == [second, first]
    assert all(offer["extraction_status"] == "queued" for offer in listed)
    # Sin extracción todavía, no hay título ni empresa que enseñar.
    assert listed[0]["title"] is None


def test_the_page_size_has_a_ceiling(api: tuple[TestClient, FakeQueue]) -> None:
    client, _ = api
    assert client.get("/api/offers", params={"limit": 500}).status_code == 422


# ---------------------------------------------------------------------------
# El detalle con la extracción hecha
# ---------------------------------------------------------------------------


async def _extract(
    sessions: async_sessionmaker[AsyncSession],
    job_run_id: str,
    builder: Any = extraction.canned_draft,
) -> None:
    """Ejecuta la tarea de verdad sobre el trabajo que dejó el endpoint."""
    await tasks.extract_offer(
        {
            "sessions": sessions,
            "llm": StubClient({extraction.PURPOSE: builder}),
            "job_try": 1,
        },
        job_run_id,
    )


async def test_the_detail_shows_each_field_with_its_evidence(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()

    assert body["extraction_status"] == "succeeded"
    assert body["extraction"]["model"] == "stub"
    assert len(body["versions"]) == 1

    fields = {field["name"]: field for field in body["extraction"]["identification"]}
    # Publicado: valor y la cita que lo sostiene.
    assert fields["title"]["evidence"]["status"] == "published"
    assert fields["title"]["evidence"]["source_quote"]
    assert fields["title"]["value"]
    # Inferido: razonamiento y confianza, sin cita.
    assert fields["role_family"]["evidence"]["status"] == "inferred"
    assert fields["role_family"]["evidence"]["reasoning"]
    assert fields["role_family"]["evidence"]["confidence"] in {"high", "medium", "low"}
    # Ausente: sin valor y sin nada que lo respalde.
    assert fields["location"]["evidence"]["status"] == "absent"
    assert fields["location"]["value"] is None


async def test_the_detail_carries_every_field_of_the_contract(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Las listas se derivan del esquema, así que no se pueden quedar cortas.

    Si alguien añade un campo al contrato y no toca nada más, tiene que
    aparecer igualmente: una lista escrita a mano se olvidaría.
    """
    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    identification = {f["name"] for f in body["extraction"]["identification"]}
    compensation = {f["name"] for f in body["extraction"]["compensation"]}

    assert identification == set(schemas.Identification.model_fields)
    assert compensation == {
        f"comp_{name}" for name in schemas.Compensation.model_fields
    }


async def test_the_two_companies_stay_apart_in_the_response(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"], lambda _: good_draft())

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    extraction_body = body["extraction"]

    assert extraction_body["posting_company"]["name"] == "Reclutamiento Bahía"
    assert extraction_body["employer_company"]["name"] == "Astillero Nube S.L."
    assert extraction_body["employer_company"]["confidence"] == "high"
    assert extraction_body["employer_company"]["evidence"]["status"] == "inferred"


async def test_what_the_code_corrected_is_visible(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Las correcciones se enseñan: son la cuenta de lo que el modelo falla."""

    def claims_the_advert_is_verified(_: str) -> schemas.ExtractionDraft:
        draft = good_draft()
        draft.identification.posting_status = published(
            vocab.PostingStatus.ACTIVE_VERIFIED, "oferta para cliente"
        )
        return draft

    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"], claims_the_advert_is_verified)

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    corrections = body["extraction"]["corrections"]

    assert [c["rule"] for c in corrections] == ["active_verified_needs_a_check"]
    assert corrections[0]["previous"] == "active_verified"
    assert corrections[0]["applied"] == "unverifiable"


async def test_the_cost_of_the_run_is_reported(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Cero con el cliente simulado, pero presente: se enseña lo que costó."""
    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    assert body["extraction"]["cost_usd"] == "0.000000"


async def test_a_failed_extraction_says_why(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    def breaks_the_contract(_: str) -> schemas.ExtractionDraft:
        draft = good_draft()
        draft.compensation.equity = absent()
        draft.compensation.equity.value = "0,5% en opciones"
        return draft

    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"], breaks_the_contract)

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    assert body["extraction_status"] == "failed"
    assert body["extraction"] is None
    assert body["extraction_error"] is not None
    assert "absent" in body["extraction_error"]


async def test_the_list_names_the_employer_and_not_the_agency(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """De un vistazo interesa para quién se trabajaría, no quién publica."""
    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"], lambda _: good_draft())

    listed = client.get("/api/offers").json()
    assert listed[0]["company"] == "Astillero Nube S.L."
    assert listed[0]["title"] == "Ingeniero de Datos"
    assert listed[0]["posting_status"] == "unverifiable"
    assert listed[0]["extraction_status"] == "succeeded"


async def test_reextracting_keeps_the_old_version(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Reextraer crea fila nueva; la anterior sigue ahí y se puede listar."""
    client, queue = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])

    again = client.post(f"/api/offers/{ingested['capture_id']}/reextract").json()
    await _extract(sessions, again["job_run_id"], lambda _: good_draft())

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    assert len(body["versions"]) == 2
    # La vigente es la última, y es la que se enseña.
    assert body["extraction"]["id"] == body["versions"][0]["id"]
    assert body["extraction"]["identification"][0]["value"] == "Ingeniero de Datos"


async def test_two_simultaneous_pastes_of_the_same_advert_do_not_collide(
    api: tuple[TestClient, FakeQueue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La carrera entre la comprobación y el INSERT, forzada a mano.

    Pasa de verdad con un doble clic en el botón de capturar, y la destapó
    el E2E corriendo sus tests en paralelo. Se simula haciendo que la
    comprobación de duplicado mienta una vez: entonces el INSERT choca con
    la unicidad de `raw_text_sha256`, que está en la base de datos
    justamente para que esto no dependa de quién llegue antes.
    """
    client, _ = api
    first = _ingest(client).json()

    real = offers_repo.find_capture_by_sha256
    calls = {"n": 0}

    async def lies_once(session: Any, sha: str) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return await real(session, sha)

    monkeypatch.setattr(offers_repo, "find_capture_by_sha256", lies_once)

    response = _ingest(client)

    # Ni 500 ni una segunda captura: se recoge la que ganó la carrera.
    assert response.status_code == 202
    assert response.json()["capture_id"] == first["capture_id"]
    assert len(client.get("/api/offers").json()) == 1
