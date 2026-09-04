"""Los endpoints de ofertas.

Todos exigen sesión: el middleware de `main.py` cierra la API por omisión y
estas rutas no están en la lista de públicas.

El endpoint de ingesta acepta **solo texto pegado**. Los otros cuatro
canales del contrato —URL, extensión, Telegram, correo— son Fase 4, y se
declaran como tal en el tipo: mandar `source: "url"` da un 422 documentado
en el OpenAPI, no una aceptación silenciosa de algo que no se sabe procesar.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Annotated, Literal

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api.jobs import queue as job_queue
from futuro_api.jobs import repository as jobs_repo
from futuro_api.models import OfferCapture
from futuro_api.offers import repository as offers_repo
from futuro_api.offers import views
from futuro_api.offers import vocabularies as vocab

router = APIRouter(prefix="/api/offers", tags=["offers"])

# Por debajo de esto no hay anuncio que extraer: el modelo devolvería
# `absent` en todo y se pagaría por nada. Es un juicio, no una regla del
# contrato.
MIN_RAW_TEXT_CHARS = 200
MAX_RAW_TEXT_CHARS = 200_000

MAX_PAGE = 100


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with factory() as session:
        yield session


def get_queue(request: Request) -> ArqRedis:
    """La cola, o un 503 si no está.

    La API arranca aunque Redis no conteste —seguir sirviendo lecturas es
    mejor que no arrancar— así que aquí es donde se nota: lo único que no se
    puede hacer sin cola es pedir una extracción nueva.
    """
    queue: ArqRedis | None = getattr(request.app.state, "queue", None)
    if queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="la cola de trabajos no está disponible",
        )
    return queue


SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]


class IngestRequest(BaseModel):
    # `Literal` y no el enum entero: los otros cuatro canales existen en el
    # contrato y en la columna, pero no hay código que sepa procesarlos.
    source: Literal[vocab.SourceChannel.PASTE] = vocab.SourceChannel.PASTE
    raw_text: str = Field(min_length=MIN_RAW_TEXT_CHARS, max_length=MAX_RAW_TEXT_CHARS)
    deadline: date | None = None
    capture_note: str | None = None
    # Con una captura repetida no se vuelve a extraer salvo que se pida:
    # sería pagar dos veces por el mismo texto.
    force_reextract: bool = False


class IngestResponse(BaseModel):
    capture_id: uuid.UUID
    raw_text_sha256: str
    duplicate: bool
    job_run_id: uuid.UUID | None = None
    extraction_status: views.ExtractionStatus
    extraction_id: uuid.UUID | None = None


async def _state_of(
    session: AsyncSession, capture_id: uuid.UUID
) -> tuple[views.ExtractionStatus, uuid.UUID | None]:
    extraction = await offers_repo.current_extraction(session, capture_id)
    run = await jobs_repo.latest_run_for_capture(session, capture_id)
    return views.status_of(run, extraction), (extraction.id if extraction else None)


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingesta una oferta pegada como texto",
)
async def ingest(
    payload: IngestRequest,
    response: Response,
    session: SessionDep,
    queue: QueueDep,
) -> IngestResponse:
    """Guarda la captura y encola su extracción.

    Devuelve 202 y no 200 porque la extracción todavía no existe: lo que se
    acepta aquí es el encargo, y el resultado llega minutos después.
    """
    raw_text_sha256 = offers_repo.sha256_of(payload.raw_text)
    existing = await offers_repo.find_capture_by_sha256(session, raw_text_sha256)

    if existing is not None and not payload.force_reextract:
        # Mismo texto, ya capturado: se devuelve lo que hay en vez de pagar
        # otra extracción idéntica. 200 y no 202 porque no se ha aceptado
        # ningún trabajo nuevo.
        response.status_code = status.HTTP_200_OK
        extraction_status, extraction_id = await _state_of(session, existing.id)
        return IngestResponse(
            capture_id=existing.id,
            raw_text_sha256=raw_text_sha256,
            duplicate=True,
            extraction_status=extraction_status,
            extraction_id=extraction_id,
        )

    capture = existing
    if capture is None:
        try:
            capture = await offers_repo.create_capture(
                session,
                source=vocab.SourceChannel.PASTE,
                raw_text=payload.raw_text,
                deadline=payload.deadline,
                capture_note=payload.capture_note,
            )
            await session.commit()
        except IntegrityError:
            # Otra petición capturó el mismo texto entre la comprobación de
            # arriba y este INSERT. La unicidad de `raw_text_sha256` está en
            # la base de datos justamente para que esto no dependa de quién
            # llegue antes: se recoge la captura que ganó y se sigue como si
            # se hubiera visto desde el principio. Pasa de verdad con un
            # doble clic en el botón, y lo destapó el E2E en paralelo.
            await session.rollback()
            capture = await offers_repo.find_capture_by_sha256(session, raw_text_sha256)
            if capture is None:  # pragma: no cover - la fila tiene que estar
                raise

    run = await job_queue.enqueue_extraction(queue, session, capture.id)
    _, extraction_id = await _state_of(session, capture.id)
    return IngestResponse(
        capture_id=capture.id,
        raw_text_sha256=raw_text_sha256,
        duplicate=existing is not None,
        job_run_id=run.id,
        extraction_status="queued",
        extraction_id=extraction_id,
    )


@router.post(
    "/{capture_id}/reextract",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Vuelve a extraer una oferta ya capturada",
)
async def reextract(
    capture_id: uuid.UUID, session: SessionDep, queue: QueueDep
) -> IngestResponse:
    """Encola una extracción nueva. No sobrescribe la anterior.

    Reextraer crea una fila nueva en `offer_extractions`, versionada por el
    prompt con el que se hizo. Es lo que permite comparar qué produjo cada
    versión sobre el mismo anuncio.
    """
    capture = await session.get(OfferCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="esa oferta no existe")

    run = await job_queue.enqueue_extraction(queue, session, capture.id)
    _, extraction_id = await _state_of(session, capture.id)
    return IngestResponse(
        capture_id=capture.id,
        raw_text_sha256=capture.raw_text_sha256,
        duplicate=False,
        job_run_id=run.id,
        extraction_status="queued",
        extraction_id=extraction_id,
    )


@router.get("", summary="Lista las ofertas capturadas")
async def list_offers(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 50,
    before: uuid.UUID | None = None,
) -> list[views.OfferSummaryView]:
    """Listado mínimo, de la más reciente a la más antigua.

    Sin filtros ni orden configurable: eso es la pantalla Pipeline, que no
    es esta rebanada. Existe para que la pantalla de una oferta siga siendo
    alcanzable después de recargar el navegador.
    """
    captures = await offers_repo.list_captures(session, limit=limit, before=before)
    capture_ids = [capture.id for capture in captures]
    extractions = await offers_repo.current_extractions_for(session, capture_ids)
    runs = await jobs_repo.latest_runs_for(session, capture_ids)

    summaries = []
    for capture in captures:
        extraction = extractions.get(capture.id)
        company = None
        if extraction is not None:
            # El empleador final manda sobre quien publica: es la empresa
            # para la que se trabajaría, que es lo que interesa de un
            # vistazo.
            named = extraction.employer_company or extraction.posting_company
            company = named.name if named else None
        summaries.append(
            views.OfferSummaryView(
                id=capture.id,
                captured_at=capture.captured_at,
                title=extraction.title if extraction else None,
                company=company,
                posting_status=extraction.posting_status if extraction else None,
                extraction_status=views.status_of(runs.get(capture.id), extraction),
            )
        )
    return summaries


@router.get("/{capture_id}", summary="Una oferta con lo que se extrajo de ella")
async def get_offer(capture_id: uuid.UUID, session: SessionDep) -> views.OfferView:
    capture = await session.get(OfferCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="esa oferta no existe")

    extraction = await offers_repo.current_extraction(session, capture_id)
    run = await jobs_repo.latest_run_for_capture(session, capture_id)
    versions = await offers_repo.extraction_versions(session, capture_id)

    cost = None
    if extraction is not None and extraction.job_run_id is not None:
        cost = await jobs_repo.cost_of_run(session, extraction.job_run_id)

    return views.OfferView(
        capture=views.capture_view(capture),
        extraction_status=views.status_of(run, extraction),
        # Solo se enseña el error cuando el trabajo acabó mal: mientras se
        # reintenta, el error del intento anterior confundiría más que
        # ayudar.
        extraction_error=(
            run.error
            if run is not None and views.status_of(run, extraction) == "failed"
            else None
        ),
        extraction=(
            views.extraction_view(extraction, cost_usd=cost)
            if extraction is not None
            else None
        ),
        versions=[
            views.VersionView(
                id=version.id,
                prompt_version=version.prompt_version,
                model=version.model,
                extracted_at=version.extracted_at,
            )
            for version in versions
        ],
    )
