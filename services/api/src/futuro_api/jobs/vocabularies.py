"""Vocabularios de la mitad operativa."""

from __future__ import annotations

from enum import StrEnum


class JobKind(StrEnum):
    """Tipos de trabajo encolado.

    Solo hay uno: las llamadas al LLM son el primer trabajo que justifica la
    cola. El scoring de M2 añadirá el suyo.
    """

    OFFER_EXTRACTION = "offer_extraction"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LlmCallStatus(StrEnum):
    """Estado de una llamada concreta al proveedor.

    `REFUSED` es un estado propio y no un fallo: con structured outputs el
    modelo puede negarse a responder, y eso no es un error de red ni un
    esquema mal formado. Confundirlos haría que un rechazo se reintentara
    para siempre.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUSED = "refused"
