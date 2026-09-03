"""Tablas de ejecuciones y de coste.

Dos tablas y no una porque `ARCHITECTURE.md` §5 pide dos cosas distintas
—ejecuciones de jobs y coste de LLM— y porque en M2 un job de scoring hará
más de una llamada al modelo. El precio es un join.

Estas tablas sí son mutables: un job pasa por `queued`, `running` y su
estado final. No son capas del contrato de datos, así que no llevan el
trigger de inmutabilidad que sí llevan `offer_captures` y `offer_extractions`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from futuro_api.db import Base, CreatedAt, UuidPk, vocabulary
from futuro_api.jobs import vocabularies as vocab

_TIMESTAMP = sa.DateTime(timezone=True)


class JobRun(Base):
    """Una ejecución de un trabajo encolado."""

    __tablename__ = "job_runs"
    __table_args__ = (
        sa.CheckConstraint("attempt >= 1", name="attempt_positive"),
        sa.Index("ix_job_runs_status_queued_at", "status", "queued_at"),
    )

    id: Mapped[UuidPk]
    kind: Mapped[vocab.JobKind] = mapped_column(
        vocabulary(vocab.JobKind, "job_kind"), nullable=False
    )
    status: Mapped[vocab.JobStatus] = mapped_column(
        vocabulary(vocab.JobStatus, "job_status"), nullable=False
    )
    # Sobre qué se trabaja. Nullable porque los trabajos que no son de una
    # oferta —avisos, por ejemplo— llegan en fases posteriores; una
    # referencia polimórfica genérica habría perdido la integridad de la FK.
    capture_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("offer_captures.id", ondelete="CASCADE"), nullable=True
    )
    # El id que devuelve arq, para poder cruzar una fila con la cola cuando
    # algo se queda a medias.
    arq_job_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True, unique=True)
    attempt: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("1")
    )
    queued_at: Mapped[CreatedAt]
    started_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(_TIMESTAMP, nullable=True)
    # Clase y mensaje del error. Nunca el `raw_text`: un fallo no es motivo
    # para duplicar el anuncio en una columna de diagnóstico.
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    llm_calls: Mapped[list[LlmCall]] = relationship(
        back_populates="job_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LlmCall.created_at",
        lazy="selectin",
    )


class LlmCall(Base):
    """Una llamada al proveedor, con su coste.

    Se guardan los tokens *y* el coste *y* la versión de la tarifa: si la
    tabla de precios estaba mal, el coste se recalcula sin haber perdido el
    dato. Es la misma propiedad que hace recalculable la capa `assessment`.
    """

    __tablename__ = "llm_calls"
    __table_args__ = (
        sa.CheckConstraint("cost_usd >= 0", name="cost_not_negative"),
        sa.CheckConstraint("latency_ms >= 0", name="latency_not_negative"),
    )

    id: Mapped[UuidPk]
    job_run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(sa.Text, nullable=False)
    provider: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Identificador de la respuesta del proveedor, para poder reclamar o
    # depurar una llamada concreta meses después.
    request_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    output_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    reasoning_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    pricing_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(sa.Numeric(10, 6), nullable=False)
    latency_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[vocab.LlmCallStatus] = mapped_column(
        vocabulary(vocab.LlmCallStatus, "llm_call_status"), nullable=False
    )
    created_at: Mapped[CreatedAt]

    job_run: Mapped[JobRun] = relationship(back_populates="llm_calls")
