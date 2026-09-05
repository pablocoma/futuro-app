"""Lo que la API devuelve del dossier mínimo."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from futuro_api.models import Application


class ApplicationView(BaseModel):
    id: uuid.UUID
    variant: str
    cv_sha256: str
    confirmed_at: datetime
    recommendation_id: uuid.UUID | None = None


def application_view(application: Application) -> ApplicationView:
    return ApplicationView(
        id=application.id,
        variant=application.variant,
        cv_sha256=application.cv_sha256,
        confirmed_at=application.confirmed_at,
        recommendation_id=application.recommendation_id,
    )
