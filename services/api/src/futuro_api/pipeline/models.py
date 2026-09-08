"""La tabla `offer_status_events`: la línea de tiempo del estado.

Ver `futuro_api/pipeline/__init__.py` para por qué es una tabla propia y no
un `ALTER TABLE` sobre `applications`.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from futuro_api.db import Base, CreatedAt, UuidPk, vocabulary
from futuro_api.pipeline.vocabularies import ApplicationStatus


class OfferStatusEvent(Base):
    """Una transición de estado. Append-only: cambiar de etapa es una fila nueva."""

    __tablename__ = "offer_status_events"
    __table_args__ = (
        sa.Index(
            "ix_offer_status_events_capture_id_occurred_at",
            "capture_id",
            sa.text("occurred_at DESC"),
        ),
    )

    id: Mapped[UuidPk]
    capture_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_captures.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        vocabulary(ApplicationStatus, "application_status"), nullable=False
    )
    occurred_at: Mapped[CreatedAt]
