"""Lo que la API devuelve al frontend.

La base de datos guarda el valor en una columna y el sobre de evidencia en
un `jsonb` aparte, porque eso es lo que permite consultar y tipar. Pero el
contrato define un campo como **valor más evidencia**, y esa es la forma que
sale por la API: la traducción entre las dos se hace aquí, una sola vez.

Las listas de campos se derivan del esquema de salida del modelo en vez de
escribirse a mano, así que añadir un campo al contrato lo hace aparecer en
la pantalla sin tocar este fichero. Una lista escrita a mano se olvida, y el
campo nuevo se guardaría sin que nadie lo viera nunca.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from futuro_api.jobs import vocabularies as jobs_vocab
from futuro_api.models import JobRun, OfferCapture, OfferExtraction
from futuro_api.offers import schemas
from futuro_api.offers import vocabularies as vocab

IDENTIFICATION_FIELDS: tuple[str, ...] = tuple(schemas.Identification.model_fields)
COMPENSATION_FIELDS: tuple[str, ...] = tuple(
    f"comp_{name}" for name in schemas.Compensation.model_fields
)

ExtractionStatus = Literal["none", "queued", "running", "succeeded", "failed"]


class EvidenceView(BaseModel):
    status: vocab.EvidenceStatus
    source_quote: str | None = None
    reasoning: str | None = None
    confidence: vocab.Confidence | None = None


class FieldView(BaseModel):
    """Un campo tal como lo define el contrato: valor y evidencia.

    `name` es el nombre de la columna, y la etiqueta legible la pone el
    frontend: cómo se llama un campo en pantalla es presentación, y no tiene
    por qué viajar en cada respuesta.
    """

    name: str
    value: Any = None
    evidence: EvidenceView


class CompanyView(BaseModel):
    id: uuid.UUID | None = None
    name: str | None = None
    confidence: vocab.EmployerConfidence | None = None
    evidence: EvidenceView


class RequirementView(BaseModel):
    position: int
    text: str
    source_quote: str
    kind: vocab.RequirementKind
    category: vocab.RequirementCategory
    # Los tres se quedan nulos en M1: cruzar contra el banco de evidencias
    # exige leer el repositorio privado, que es M3.
    match: vocab.RequirementMatch | None = None
    evidence_ref: str | None = None
    cv_action: vocab.CvAction | None = None


class AnomalyView(BaseModel):
    position: int
    requirement_position: int | None = None
    text: str
    explanation: str
    source_quote: str


class CorrectionView(BaseModel):
    """Algo que el código le corrigió al modelo.

    Se enseña en pantalla a propósito: es la cuenta de cuántas veces el
    modelo se salta las reglas, y el dato que dice si hay que cambiar el
    prompt.
    """

    field: str
    rule: str
    detail: str
    previous: str | None = None
    applied: str | None = None


class ExtractionView(BaseModel):
    id: uuid.UUID
    prompt_version: str
    model: str
    extracted_at: datetime
    cost_usd: str | None = None
    identification: list[FieldView]
    compensation: list[FieldView]
    responsibilities: FieldView
    posting_company: CompanyView
    employer_company: CompanyView
    requirements: list[RequirementView]
    anomalies: list[AnomalyView]
    corrections: list[CorrectionView]


class CaptureView(BaseModel):
    id: uuid.UUID
    source: vocab.SourceChannel
    source_url: str | None = None
    captured_at: datetime
    raw_text: str
    raw_text_sha256: str
    deadline: date | None = None
    capture_note: str | None = None


class VersionView(BaseModel):
    id: uuid.UUID
    prompt_version: str
    model: str
    extracted_at: datetime


class OfferView(BaseModel):
    capture: CaptureView
    extraction_status: ExtractionStatus
    extraction_error: str | None = None
    extraction: ExtractionView | None = None
    versions: list[VersionView]


class OfferSummaryView(BaseModel):
    id: uuid.UUID
    captured_at: datetime
    title: str | None = None
    company: str | None = None
    posting_status: vocab.PostingStatus | None = None
    extraction_status: ExtractionStatus


def readable(value: Any) -> Any:
    """Un valor listo para pintar.

    Los `Decimal` salen como cadena y no como número: en JSON un número en
    coma flotante pierde exactitud, y estos son importes. `normalize` quita
    los ceros de más, para que tres años sean «3» y no «3.0».
    """
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return value


def _field(extraction: OfferExtraction, name: str) -> FieldView:
    evidence = extraction.evidence.get(name) or {
        # Un campo sin sobre no debería existir: `rules.py` rechaza la
        # extracción antes de llegar aquí. Si aparece, se enseña como
        # ausente en vez de reventar la pantalla entera.
        "status": vocab.EvidenceStatus.ABSENT.value
    }
    return FieldView(
        name=name,
        value=readable(getattr(extraction, name, None)),
        evidence=EvidenceView(**evidence),
    )


def extraction_view(
    extraction: OfferExtraction, *, cost_usd: Decimal | None
) -> ExtractionView:
    return ExtractionView(
        id=extraction.id,
        prompt_version=extraction.prompt_version,
        model=extraction.model,
        extracted_at=extraction.extracted_at,
        cost_usd=format(cost_usd, "f") if cost_usd is not None else None,
        identification=[_field(extraction, name) for name in IDENTIFICATION_FIELDS],
        compensation=[_field(extraction, name) for name in COMPENSATION_FIELDS],
        responsibilities=_field(extraction, "responsibilities"),
        posting_company=CompanyView(
            id=extraction.posting_company_id,
            name=(
                extraction.posting_company.name if extraction.posting_company else None
            ),
            evidence=EvidenceView(
                **(
                    extraction.evidence.get("posting_company_id")
                    or {"status": vocab.EvidenceStatus.ABSENT.value}
                )
            ),
        ),
        employer_company=CompanyView(
            id=extraction.employer_company_id,
            name=(
                extraction.employer_company.name
                if extraction.employer_company
                else None
            ),
            confidence=extraction.employer_confidence,
            evidence=EvidenceView(
                **(
                    extraction.evidence.get("employer_company_id")
                    or {"status": vocab.EvidenceStatus.ABSENT.value}
                )
            ),
        ),
        requirements=[
            RequirementView(
                position=requirement.position,
                text=requirement.text,
                source_quote=requirement.source_quote,
                kind=requirement.kind,
                category=requirement.category,
                match=requirement.match,
                evidence_ref=requirement.evidence_ref,
                cv_action=requirement.cv_action,
            )
            for requirement in extraction.requirements
        ],
        anomalies=[
            AnomalyView(
                position=anomaly.position,
                requirement_position=(
                    anomaly.requirement.position if anomaly.requirement else None
                ),
                text=anomaly.text,
                explanation=anomaly.explanation,
                source_quote=anomaly.source_quote,
            )
            for anomaly in extraction.anomalies
        ],
        corrections=[
            CorrectionView(**correction) for correction in extraction.corrections
        ],
    )


def status_of(run: JobRun | None, produced: object | None) -> ExtractionStatus:
    """En qué punto está un trabajo de una oferta.

    Se mira el último trabajo y no si existe el resultado, porque las dos
    cosas conviven: al reextraer hay una extracción vigente y un trabajo en
    curso a la vez, y la pantalla tiene que poder decirlo.

    `produced` es lo que el trabajo produce —la extracción vigente, o el
    assessment vigente— y por eso está tipado como `object | None`: lo único
    que se le pregunta es si existe. La alternativa era una segunda función
    idéntica en `assessment/views.py`, y dos definiciones de «en qué punto
    está esto» acaban discrepando.

    El caso raro que hay que tratar aparte: un trabajo `succeeded` cuyo
    resultado ya no está vigente. Pasa en la ventana entre que una
    reextracción termina y su puntuación se encola: el último trabajo de
    puntuación es el de la extracción anterior y dice `succeeded`, pero la
    extracción de ahora no está puntuada. Decir «puntuada» ahí sería
    mentir, así que se dice «sin puntuar».
    """
    if run is None:
        return "succeeded" if produced is not None else "none"
    if run.status is jobs_vocab.JobStatus.SUCCEEDED and produced is None:
        return "none"
    by_status: dict[jobs_vocab.JobStatus, ExtractionStatus] = {
        jobs_vocab.JobStatus.QUEUED: "queued",
        jobs_vocab.JobStatus.RUNNING: "running",
        jobs_vocab.JobStatus.SUCCEEDED: "succeeded",
        jobs_vocab.JobStatus.FAILED: "failed",
    }
    return by_status[run.status]


def capture_view(capture: OfferCapture) -> CaptureView:
    return CaptureView(
        id=capture.id,
        source=capture.source,
        source_url=capture.source_url,
        captured_at=capture.captured_at,
        raw_text=capture.raw_text,
        raw_text_sha256=capture.raw_text_sha256,
        deadline=capture.deadline,
        capture_note=capture.capture_note,
    )
