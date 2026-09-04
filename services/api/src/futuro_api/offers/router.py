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

from futuro_api.assessment import repository as assessment_repo
from futuro_api.assessment import views as assessment_views
from futuro_api.jobs import queue as job_queue
from futuro_api.jobs import repository as jobs_repo
from futuro_api.jobs import vocabularies as jobs_vocab
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
    run = await jobs_repo.latest_run_for_capture(
        session, capture_id, kind=jobs_vocab.JobKind.OFFER_EXTRACTION
    )
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


class AssessResponse(BaseModel):
    capture_id: uuid.UUID
    extraction_id: uuid.UUID
    job_run_id: uuid.UUID
    assessment_status: assessment_views.AssessmentStatus


@router.post(
    "/{capture_id}/assess",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Vuelve a puntuar una oferta ya extraída",
)
async def assess(
    capture_id: uuid.UUID, session: SessionDep, queue: QueueDep
) -> AssessResponse:
    """Encola una puntuación nueva. No sobrescribe la anterior.

    En el camino normal no hace falta llamarlo: la extracción encadena la
    puntuación al terminar bien. Existe para tres casos que sí pasan —que el
    encolado encadenado fallara, que el repositorio de datos no estuviera
    cuando tocaba, y que se quiera repuntuar una oferta concreta tras tocar
    el modelo de scoring— y es el botón que la pantalla enseña cuando una
    oferta se queda sin puntuar.

    Repuntuar el histórico entero no es esto: es
    `python -m futuro_api.assessment.recompute`, que no llama al modelo.
    Este endpoint sí llama, porque también vuelve a elegir variante.
    """
    capture = await session.get(OfferCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="esa oferta no existe")

    extraction = await offers_repo.current_extraction(session, capture_id)
    if extraction is None:
        # 409 y no 404: la oferta existe, lo que no existe todavía es algo
        # que puntuar. Un 404 haría pensar que la URL está mal.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "esa oferta no tiene ninguna extracción vigente todavía, así "
                "que no hay nada que puntuar"
            ),
        )

    run = await job_queue.enqueue_assessment(queue, session, capture_id)
    return AssessResponse(
        capture_id=capture_id,
        extraction_id=extraction.id,
        job_run_id=run.id,
        assessment_status="queued",
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
    runs = await jobs_repo.latest_runs_for(
        session, capture_ids, kind=jobs_vocab.JobKind.OFFER_EXTRACTION
    )

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


class OfferDetail(views.OfferView):
    """La oferta entera: captura, extracción, puntuación y variante.

    Hereda de `views.OfferView` en vez de anidarla, así que las claves que
    M1 ya devolvía siguen exactamente donde estaban y M2 solo añade. La
    herencia es también lo que evita que `offers/views.py` tenga que
    importar `assessment/views.py`: la dirección de las dependencias es
    `assessment` → `offers`, y el router es el único sitio que ve las dos
    mitades.
    """

    assessment_status: assessment_views.AssessmentStatus
    assessment_error: str | None = None
    assessment: assessment_views.AssessmentView | None = None
    variant_recommendation: assessment_views.VariantRecommendationView | None = None
    assessment_versions: list[assessment_views.AssessmentVersionView] = []


@router.get("/{capture_id}", summary="Una oferta con lo que se extrajo de ella")
async def get_offer(capture_id: uuid.UUID, session: SessionDep) -> OfferDetail:
    capture = await session.get(OfferCapture, capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="esa oferta no existe")

    extraction = await offers_repo.current_extraction(session, capture_id)
    run = await jobs_repo.latest_run_for_capture(
        session, capture_id, kind=jobs_vocab.JobKind.OFFER_EXTRACTION
    )
    versions = await offers_repo.extraction_versions(session, capture_id)

    cost = None
    if extraction is not None and extraction.job_run_id is not None:
        cost = await jobs_repo.cost_of_run(session, extraction.job_run_id)

    assessment = None
    variant = None
    assessment_versions: list[assessment_views.AssessmentVersionView] = []
    assessment_view = None
    if extraction is not None:
        assessment = await assessment_repo.current_assessment(session, extraction.id)
        variant = await assessment_repo.current_variant_recommendation(
            session, extraction.id
        )
        assessment_versions = [
            assessment_views.AssessmentVersionView(
                id=version.id,
                assessed_at=version.assessed_at,
                source=version.source,
                scoring_model_version=version.scoring_model_version,
                value_score=(
                    format(version.value_score, "f")
                    if version.value_score is not None
                    else None
                ),
            )
            for version in await assessment_repo.assessment_versions(
                session, extraction.id
            )
        ]
    assessment_run = await jobs_repo.latest_run_for_capture(
        session, capture_id, kind=jobs_vocab.JobKind.OFFER_ASSESSMENT
    )
    assessment_status = views.status_of(assessment_run, assessment)
    if assessment is not None and extraction is not None:
        assessment_view = assessment_views.assessment_view(
            assessment,
            total_weight=assessment_views.total_weight_of(assessment),
            requirement_texts={
                requirement.id: (requirement.position, requirement.text)
                for requirement in extraction.requirements
            },
            cost_usd=await assessment_repo.cost_of_assessment(session, assessment),
        )

    return OfferDetail(
        capture=views.capture_view(capture),
        extraction_status=views.status_of(run, extraction),
        assessment_status=assessment_status,
        assessment_error=(
            assessment_run.error
            if assessment_run is not None and assessment_status == "failed"
            else None
        ),
        assessment=assessment_view,
        variant_recommendation=(
            assessment_views.variant_view(variant) if variant is not None else None
        ),
        assessment_versions=assessment_versions,
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
