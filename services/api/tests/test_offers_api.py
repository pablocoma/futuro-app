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

from futuro_api.assessment import calls as assessment_calls
from futuro_api.jobs import tasks
from futuro_api.jobs.tasks import extract_offer
from futuro_api.llm.stub import StubClient
from futuro_api.offers import extraction, schemas
from futuro_api.offers import repository as offers_repo
from futuro_api.offers import vocabularies as vocab
from tests.conftest import DATA_REPO, FakeQueue, client_with_queue, make_settings
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


# ---------------------------------------------------------------------------
# La puntuación en la respuesta del detalle
# ---------------------------------------------------------------------------


async def _score(sessions: async_sessionmaker[AsyncSession], job_run_id: str) -> None:
    """Ejecuta la tarea de puntuación de verdad, contra el repo sintético."""
    await tasks.assess_offer(
        {
            "sessions": sessions,
            "llm": StubClient(
                {
                    assessment_calls.SCORING_PURPOSE: assessment_calls.canned_scoring,
                    assessment_calls.VARIANT_PURPOSE: assessment_calls.canned_variant,
                }
            ),
            "settings": make_settings(data_repo_path=str(DATA_REPO)),
            "job_try": 1,
        },
        job_run_id,
    )


async def _extracted_and_scored(
    client: TestClient, sessions: async_sessionmaker[AsyncSession]
) -> str:
    """Una oferta pegada, extraída y puntuada por los caminos reales."""
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])
    queued = client.post(f"/api/offers/{ingested['capture_id']}/assess").json()
    await _score(sessions, queued["job_run_id"])
    return str(ingested["capture_id"])


async def test_an_offer_without_an_extraction_cannot_be_assessed_yet(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """409 y no 404: la oferta existe, lo que no existe es qué puntuar.

    Un 404 haría pensar que la URL está mal.
    """
    client, _ = api
    ingested = _ingest(client).json()
    response = client.post(f"/api/offers/{ingested['capture_id']}/assess")
    assert response.status_code == 409
    assert "nada que puntuar" in response.json()["detail"]


def test_assessing_an_offer_that_does_not_exist_is_a_404(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api
    response = client.post("/api/offers/00000000-0000-0000-0000-000000000000/assess")
    assert response.status_code == 404


async def test_an_unscored_offer_says_so_without_inventing_anything(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    assert body["assessment_status"] == "none"
    assert body["assessment"] is None
    assert body["variant_recommendation"] is None
    # Y la extracción sigue estando: una cosa no depende de la otra.
    assert body["extraction"] is not None


async def test_the_detail_carries_the_weighted_composition(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """La pantalla no hace aritmética: recibe el ancho y el alto ya hechos.

    Si dividiera pesos para sacar anchos, habría dos sitios donde se calcula
    lo mismo, y el día que discreparan el dibujo diría una cosa y la
    puntuación otra.
    """
    client, _ = api
    capture_id = await _extracted_and_scored(client, sessions)

    body = client.get(f"/api/offers/{capture_id}").json()
    assert body["assessment_status"] == "succeeded"
    assessment = body["assessment"]

    # Las cuatro dimensiones del modelo sintético, en su orden, puntuadas o
    # no: ocultar las que no se pudieron puntuar es lo que la pantalla tiene
    # prohibido hacer.
    dimensions = assessment["dimensions"]
    assert [d["dimension"] for d in dimensions] == [
        "ahorro_estimado",
        "aprendizaje",
        "ubicacion",
        "encaje_de_rol",
    ]
    # Los anchos suman uno: son la fracción del peso **total**, así que la
    # barra ancha y vacía enseña cuánto peso se perdió.
    assert sum(d["weight_share"] for d in dimensions) == pytest.approx(1.0)
    scored = [d for d in dimensions if d["score"] is not None]
    unscored = [d for d in dimensions if d["score"] is None]
    assert scored and unscored
    for dimension in scored:
        assert dimension["citation"], "una nota sin cita no debería haber entrado"
        assert dimension["score_share"] == pytest.approx(dimension["score"] / 5)
    for dimension in unscored:
        assert dimension["unscored_reason"]
        assert dimension["score_share"] is None


async def test_the_detail_carries_the_gates_and_what_the_code_computed(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client, _ = api
    capture_id = await _extracted_and_scored(client, sessions)

    assessment = client.get(f"/api/offers/{capture_id}").json()["assessment"]
    assert [g["gate"] for g in assessment["gates"]] == [
        "permiso_de_trabajo",
        "suelo_de_ahorro",
        "condiciones_aceptables",
    ]
    # `value_score` viaja como el texto exacto de la base de datos, igual
    # que los importes en M1: es la puntuación, no geometría.
    assert assessment["value_score"] == "3.00"
    assert assessment["coverage"] == "0.700"
    assert assessment["effort_tier"] in {"full", "standard", "cheap", "skip"}
    assert assessment["source"] == "llm"
    assert len(assessment["scoring_model_sha256"]) == 64
    # Cero y no nulo: el cliente simulado sí llama, pero no cobra. «No
    # consta» sería nulo, y es lo que devuelve un assessment recalculado.
    assert assessment["cost_usd"] == "0.000000"


async def test_the_detail_carries_the_recommended_variant_with_its_reason(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """`ARCHITECTURE.md` §7: la app enseña *ese razonamiento* junto al PDF."""
    client, _ = api
    capture_id = await _extracted_and_scored(client, sessions)

    variant = client.get(f"/api/offers/{capture_id}").json()["variant_recommendation"]
    assert variant["variant"] == "cartografia_nautica"
    assert variant["confidence"] == "low"
    assert "simulad" in variant["reason"]


async def test_the_detail_crosses_requirements_against_the_evidence_bank(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Los campos que M1 dejó a NULL, ahora rellenos y en otra tabla.

    `offer_requirements.match` sigue en NULL —esa capa es inmutable y el
    cruce tiene que poder recalcularse— y el cruce vive en la capa
    `assessment`. Aquí se ve que la respuesta lleva las dos cosas sin
    confundirlas.
    """
    client, _ = api
    capture_id = await _extracted_and_scored(client, sessions)

    body = client.get(f"/api/offers/{capture_id}").json()
    assert all(
        requirement["match"] is None
        for requirement in body["extraction"]["requirements"]
    )
    matches = body["assessment"]["requirement_matches"]
    assert matches
    for match in matches:
        assert match["requirement_text"]
        if match["match"] == "meets":
            assert match["evidence_ref"], "un `meets` sin referencia no debería estar"


async def test_a_failed_assessment_says_why_and_keeps_the_extraction(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Sin repositorio de datos no se puntúa, y todo lo demás sigue.

    Es el camino que hay hoy en la VM, donde el clon de solo lectura es M3.
    """
    client, _ = api
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])
    queued = client.post(f"/api/offers/{ingested['capture_id']}/assess").json()
    await tasks.assess_offer(
        {
            "sessions": sessions,
            "llm": StubClient({}),
            "settings": make_settings(data_repo_path=""),
            "job_try": 1,
        },
        queued["job_run_id"],
    )

    body = client.get(f"/api/offers/{ingested['capture_id']}").json()
    assert body["assessment_status"] == "failed"
    assert "DATA_REPO_PATH" in body["assessment_error"]
    assert body["assessment"] is None
    assert body["extraction"] is not None


async def test_reextracting_leaves_the_new_reading_unscored(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """El caso raro que obligó a tocar `status_of`.

    Tras reextraer, el último trabajo de puntuación es el de la extracción
    **anterior** y dice `succeeded`, pero la lectura de ahora no está
    puntuada. Decir «puntuada» ahí sería mentir.
    """
    client, _ = api
    capture_id = await _extracted_and_scored(client, sessions)
    reextracted = client.post(f"/api/offers/{capture_id}/reextract").json()
    await _extract(sessions, reextracted["job_run_id"])

    body = client.get(f"/api/offers/{capture_id}").json()
    assert body["extraction_status"] == "succeeded"
    assert body["assessment_status"] == "none"
    assert body["assessment"] is None


async def test_rescoring_keeps_the_previous_assessment_visible(
    api: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Append-only: la lista de versiones es lo que lo hace visible.

    Es lo que enseña que dos ofertas puntuadas con modelos de scoring
    distintos no son comparables.
    """
    client, _ = api
    capture_id = await _extracted_and_scored(client, sessions)
    again = client.post(f"/api/offers/{capture_id}/assess").json()
    await _score(sessions, again["job_run_id"])

    body = client.get(f"/api/offers/{capture_id}").json()
    assert len(body["assessment_versions"]) == 2
    assert body["assessment"]["id"] == body["assessment_versions"][0]["id"]


# ---------------------------------------------------------------------------
# El dossier minimo: descargar el PDF y confirmar variante (M3)
# ---------------------------------------------------------------------------


async def test_downloading_without_a_variant_serves_the_recommendation(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Sin `?variant=`, y sin ninguna confirmada todavía: la del modelo."""
    client, _ = api_with_data_repo
    capture_id = await _extracted_and_scored(client, sessions)

    response = client.get(f"/api/offers/{capture_id}/cv")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    expected = next(
        (DATA_REPO / "cv" / "variants" / "cartografia_nautica").glob("*.pdf")
    )
    assert response.content == expected.read_bytes()


async def test_downloading_a_specific_variant(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Se puede mirar cualquier variante disponible antes de confirmarla."""
    client, _ = api_with_data_repo
    capture_id = await _extracted_and_scored(client, sessions)

    response = client.get(
        f"/api/offers/{capture_id}/cv", params={"variant": "sistemas_gis"}
    )
    assert response.status_code == 200
    expected = next((DATA_REPO / "cv" / "variants" / "sistemas_gis").glob("*.pdf"))
    assert response.content == expected.read_bytes()


async def test_downloading_an_unavailable_variant_is_a_422(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client, _ = api_with_data_repo
    capture_id = await _extracted_and_scored(client, sessions)

    response = client.get(
        f"/api/offers/{capture_id}/cv", params={"variant": "no_existe"}
    )
    assert response.status_code == 422


async def test_downloading_without_any_recommendation_is_a_409(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Extraída pero sin puntuar: no hay variante que servir sin decir cuál."""
    client, _ = api_with_data_repo
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])

    response = client.get(f"/api/offers/{ingested['capture_id']}/cv")
    assert response.status_code == 409


def test_downloading_without_the_data_repo_is_a_503(
    api: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api
    ingested = _ingest(client).json()
    response = client.get(f"/api/offers/{ingested['capture_id']}/cv")
    assert response.status_code == 503


def test_downloading_for_an_offer_that_does_not_exist_is_a_404(
    api_with_data_repo: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api_with_data_repo
    response = client.get("/api/offers/00000000-0000-0000-0000-000000000000/cv")
    assert response.status_code == 404


async def test_confirming_a_variant_records_the_dossier(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Confirmar registra el PDF exacto y de qué recomendación partió."""
    client, _ = api_with_data_repo
    capture_id = await _extracted_and_scored(client, sessions)

    response = client.post(
        f"/api/offers/{capture_id}/dossier", json={"variant": "cartografia_nautica"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["variant"] == "cartografia_nautica"
    assert len(body["cv_sha256"]) == 64
    assert body["recommendation_id"] is not None

    detail = client.get(f"/api/offers/{capture_id}").json()
    assert detail["application"]["variant"] == "cartografia_nautica"


async def test_confirming_a_variant_without_a_recommendation_leaves_it_null(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Nada impide confirmar sin que exista recomendación: los PDF ya existen."""
    client, _ = api_with_data_repo
    ingested = _ingest(client).json()
    await _extract(sessions, ingested["job_run_id"])

    response = client.post(
        f"/api/offers/{ingested['capture_id']}/dossier",
        json={"variant": "sistemas_gis"},
    )
    assert response.status_code == 201
    assert response.json()["recommendation_id"] is None


async def test_confirming_an_unavailable_variant_is_a_422(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client, _ = api_with_data_repo
    capture_id = await _extracted_and_scored(client, sessions)
    response = client.post(
        f"/api/offers/{capture_id}/dossier", json={"variant": "no_existe"}
    )
    assert response.status_code == 422


async def test_changing_the_variant_creates_a_new_row_and_it_becomes_current(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Nunca sobrescribe: cambiar de variante es una fila nueva."""
    client, _ = api_with_data_repo
    capture_id = await _extracted_and_scored(client, sessions)

    client.post(
        f"/api/offers/{capture_id}/dossier", json={"variant": "cartografia_nautica"}
    )
    client.post(f"/api/offers/{capture_id}/dossier", json={"variant": "sistemas_gis"})

    detail = client.get(f"/api/offers/{capture_id}").json()
    assert detail["application"]["variant"] == "sistemas_gis"

    # Y la descarga sin variante explícita sigue lo confirmado, no lo
    # recomendado -que sigue siendo "cartografia_nautica"-.
    download = client.get(f"/api/offers/{capture_id}/cv")
    expected = next((DATA_REPO / "cv" / "variants" / "sistemas_gis").glob("*.pdf"))
    assert download.content == expected.read_bytes()


def test_confirming_for_an_offer_that_does_not_exist_is_a_404(
    api_with_data_repo: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api_with_data_repo
    response = client.post(
        "/api/offers/00000000-0000-0000-0000-000000000000/dossier",
        json={"variant": "sistemas_gis"},
    )
    assert response.status_code == 404


async def test_the_detail_shows_no_application_until_one_is_confirmed(
    api_with_data_repo: tuple[TestClient, FakeQueue],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    client, _ = api_with_data_repo
    capture_id = await _extracted_and_scored(client, sessions)
    body = client.get(f"/api/offers/{capture_id}").json()
    assert body["application"] is None


def test_the_detail_lists_the_available_variants(
    api_with_data_repo: tuple[TestClient, FakeQueue],
) -> None:
    client, _ = api_with_data_repo
    capture_id = _ingest(client).json()["capture_id"]
    body = client.get(f"/api/offers/{capture_id}").json()
    assert set(body["available_variants"]) == {
        "topografia_urbana",
        "sistemas_gis",
        "cartografia_nautica",
        "teledeteccion",
    }


def test_the_detail_shows_no_variants_without_the_data_repo(
    api: tuple[TestClient, FakeQueue],
) -> None:
    """Un repositorio de datos ausente no tumba el resto del detalle."""
    client, _ = api
    capture_id = _ingest(client).json()["capture_id"]
    response = client.get(f"/api/offers/{capture_id}")
    assert response.status_code == 200
    assert response.json()["available_variants"] == []
