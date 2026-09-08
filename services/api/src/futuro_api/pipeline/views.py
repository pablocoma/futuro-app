"""Lo que la API devuelve del estado de una candidatura."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from futuro_api.pipeline.models import OfferStatusEvent
from futuro_api.pipeline.vocabularies import ApplicationStatus


class StatusEventView(BaseModel):
    status: ApplicationStatus
    occurred_at: datetime


def status_event_view(event: OfferStatusEvent) -> StatusEventView:
    return StatusEventView(status=event.status, occurred_at=event.occurred_at)
