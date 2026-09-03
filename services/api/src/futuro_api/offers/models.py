"""Tablas de las capas `capture` y `extraction` del contrato.

Tres decisiones de forma que no vienen dadas por el contrato y conviene leer
antes de tocar nada:

**La captura es la oferta.** No hay tabla `offers` por encima. El contrato
escribe `offer.posting_company_id`, pero `employer_confidence` es una
inferencia del modelo: si viviera en una fila estable, reextraer con otro
`prompt_version` la sobrescribiría y se rompería la inmutabilidad que
justifica separar las capas. Así que las referencias a empresa cuelgan de la
extracción, y la identidad estable de la oferta es la captura.

**El valor va en columna tipada y el sobre de evidencia en `evidence`.** Un
sobre por campo (`status`, `source_quote`, `reasoning`, `confidence`) serían
casi noventa columnas; un jsonb con todo dentro perdería los tipos y los
CHECK que M2 necesita para puntuar leyendo SQL. Un campo `absent` es columna
`NULL` más `evidence[campo].status == "absent"`.

**`companies` solo identifica.** Todo lo que el modelo *afirme* sobre una
empresa vive en la extracción, que es donde vive la evidencia.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from futuro_api.db import Base, CreatedAt, UuidPk, vocabulary
from futuro_api.offers import vocabularies as vocab

_TIMESTAMP = sa.DateTime(timezone=True)


class Company(Base):
    """Identidad de una empresa, y nada más.

    `sector`, `size` y `funding_stage` —que el contrato pide con su evidencia
    cada uno— no están: de un texto pegado no salen honestamente, y
    rellenarlos desde el anuncio sería exactamente el `absent` con estimación
    que el contrato prohíbe. Entran cuando exista un paso de investigación,
    en una migración aditiva.
    """

    __tablename__ = "companies"

    id: Mapped[UuidPk]
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Clave de deduplicación: `name` normalizado. Deliberadamente
    # conservadora: dos filas para una misma empresa se arreglan fusionando;
    # una fusión falsa pierde información y no se deshace.
    name_key: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    created_at: Mapped[CreatedAt]


class OfferCapture(Base):
    """Capa 1. Inmutable: la prueba de qué llegó y cuándo.

    La inmutabilidad no es solo una convención del repositorio: la migración
    instala un trigger `BEFORE UPDATE` que la impone en la base de datos.
    `DELETE` sí está permitido —inmutable no es imborrable— y arrastra en
    cascada las extracciones.
    """

    __tablename__ = "offer_captures"
    __table_args__ = (
        sa.CheckConstraint("length(raw_text) > 0", name="raw_text_not_empty"),
        sa.Index("ix_offer_captures_captured_at", sa.text("captured_at DESC")),
    )

    id: Mapped[UuidPk]
    # La columna acepta los cinco canales del contrato aunque en M1 el
    # endpoint solo admita `paste`: la restricción es del canal, no del
    # esquema, y los otros cuatro son Fase 4.
    source: Mapped[vocab.SourceChannel] = mapped_column(
        vocabulary(vocab.SourceChannel, "source_channel"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    captured_at: Mapped[CreatedAt]
    raw_text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Único a propósito: reingestar el mismo texto devuelve la captura que ya
    # había en vez de pagar dos veces por la misma extracción. La invariante
    # la impone la base de datos y no la buena voluntad del endpoint.
    raw_text_sha256: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, unique=True
    )
    deadline: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    capture_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    extractions: Mapped[list[OfferExtraction]] = relationship(
        back_populates="capture",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="desc(OfferExtraction.extracted_at)",
    )


class OfferExtraction(Base):
    """Capa 2. Inmutable y versionada por `prompt_version`.

    Sin `unique(capture_id, prompt_version)` a propósito: reextraer tras un
    fallo con la misma versión tiene que poder crear fila. La extracción
    vigente es la última por `(extracted_at, id)`; no hay flag `is_current`,
    porque un flag mutable en una tabla inmutable es una contradicción que se
    paga tarde. Si algún día hay que fijar una versión concreta, el cambio
    aditivo es un `current_extraction_id` en la captura.
    """

    __tablename__ = "offer_extractions"
    __table_args__ = (
        # La regla del contrato: nunca `active_verified` sin fecha de
        # comprobación. En M1 es doblemente inalcanzable, porque de un texto
        # pegado no hay nada que comprobar.
        sa.CheckConstraint(
            "posting_status <> 'active_verified' OR status_checked_at IS NOT NULL",
            name="active_verified_needs_checked_at",
        ),
        # Empleador final inferido obliga a decir con cuánta confianza.
        sa.CheckConstraint(
            "employer_company_id IS NULL OR employer_confidence IS NOT NULL",
            name="employer_needs_confidence",
        ),
        sa.Index(
            "ix_offer_extractions_capture_id_extracted_at",
            "capture_id",
            sa.text("extracted_at DESC"),
        ),
    )

    id: Mapped[UuidPk]
    capture_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_captures.id", ondelete="CASCADE"), nullable=False
    )
    # Un job produce como mucho una extracción, y el índice único lo impone.
    # Por eso `job_runs` no guarda el camino de vuelta: una FK circular entre
    # las dos tablas sería redundante y obligaría a un UPDATE posterior.
    job_run_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("job_runs.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    prompt_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    extracted_at: Mapped[CreatedAt]

    # Sobres de evidencia, uno por campo: {campo: {status, source_quote?,
    # reasoning?, confidence?}}. La regla transversal del contrato la impone
    # `rules.py` en Python, porque un CHECK que recorra un jsonb campo a
    # campo sería ilegible y se quedaría desactualizado al añadir campos.
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Lo que el código le corrigió al modelo, para que sea visible en
    # pantalla y contable: cuántas veces se salta las reglas.
    corrections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )

    # --- Identificación -----------------------------------------------
    title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    role_family: Mapped[vocab.RoleFamily | None] = mapped_column(
        vocabulary(vocab.RoleFamily, "role_family"), nullable=True
    )
    seniority_label: Mapped[vocab.SeniorityLabel | None] = mapped_column(
        vocabulary(vocab.SeniorityLabel, "seniority_label"), nullable=True
    )
    # Años exigidos, leídos como el mínimo: si el anuncio pide "3-5 años", el
    # requisito es 3. Lo dice el prompt, y `rules.py` no acepta otra lectura.
    experience_years_required: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(4, 1), nullable=True
    )
    location: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    work_mode: Mapped[vocab.WorkMode | None] = mapped_column(
        vocabulary(vocab.WorkMode, "work_mode"), nullable=True
    )
    hiring_regions: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.Text), nullable=True
    )
    language_of_work: Mapped[list[str] | None] = mapped_column(
        ARRAY(sa.Text), nullable=True
    )
    contract_vehicle: Mapped[vocab.ContractVehicle | None] = mapped_column(
        vocabulary(vocab.ContractVehicle, "contract_vehicle"), nullable=True
    )
    posting_status: Mapped[vocab.PostingStatus] = mapped_column(
        vocabulary(vocab.PostingStatus, "posting_status"), nullable=False
    )
    status_checked_at: Mapped[datetime | None] = mapped_column(
        _TIMESTAMP, nullable=True
    )
    responsibilities: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'::text[]")
    )

    # --- Empresas: dos referencias distintas, nunca un campo fundido ---
    posting_company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True
    )
    employer_company_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True
    )
    employer_confidence: Mapped[vocab.EmployerConfidence | None] = mapped_column(
        vocabulary(vocab.EmployerConfidence, "employer_confidence"), nullable=True
    )

    # --- Compensación: solo si está publicada -------------------------
    comp_amount_min: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(12, 2), nullable=True
    )
    comp_amount_max: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(12, 2), nullable=True
    )
    comp_currency: Mapped[str | None] = mapped_column(sa.String(3), nullable=True)
    comp_period: Mapped[vocab.CompensationPeriod | None] = mapped_column(
        vocabulary(vocab.CompensationPeriod, "compensation_period"), nullable=True
    )
    comp_basis: Mapped[vocab.CompensationBasis | None] = mapped_column(
        vocabulary(vocab.CompensationBasis, "compensation_basis"), nullable=True
    )
    comp_bonus_pct: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(5, 2), nullable=True
    )
    comp_bonus_type: Mapped[vocab.BonusType | None] = mapped_column(
        vocabulary(vocab.BonusType, "bonus_type"), nullable=True
    )
    comp_equity: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    comp_territorial_adjustment: Mapped[vocab.TerritorialAdjustment | None] = (
        mapped_column(
            vocabulary(vocab.TerritorialAdjustment, "territorial_adjustment"),
            nullable=True,
        )
    )

    capture: Mapped[OfferCapture] = relationship(back_populates="extractions")
    posting_company: Mapped[Company | None] = relationship(
        foreign_keys=[posting_company_id], lazy="selectin"
    )
    employer_company: Mapped[Company | None] = relationship(
        foreign_keys=[employer_company_id], lazy="selectin"
    )
    requirements: Mapped[list[OfferRequirement]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OfferRequirement.position",
        lazy="selectin",
    )
    anomalies: Mapped[list[OfferAnomaly]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OfferAnomaly.position",
        lazy="selectin",
    )


class OfferRequirement(Base):
    """Una fila por requisito, como pide el contrato.

    `match`, `evidence_ref` y `cv_action` se quedan en NULL en toda la tabla
    durante M1: cruzar un requisito contra el banco de evidencias exige leer
    el repositorio privado, y ese clon es M3. NULL significa «sin evaluar»,
    que no es lo mismo que `no_evidence`, «evaluado y no hay nada». El CHECK
    y su gemelo en `rules.py` entran ya, con tests, para que cuando M2 los
    rellene la regla lleve tiempo aguantando peso.
    """

    __tablename__ = "offer_requirements"
    __table_args__ = (
        # La prohibición central del contrato: sin referencia a una
        # evidencia, el máximo es `partial`.
        sa.CheckConstraint(
            "match <> 'meets' OR evidence_ref IS NOT NULL",
            name="meets_needs_evidence_ref",
        ),
        sa.UniqueConstraint("extraction_id", "position"),
    )

    id: Mapped[UuidPk]
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_extractions.id", ondelete="CASCADE"), nullable=False
    )
    # Orden en el anuncio: un requisito no se entiende igual el primero que
    # el último, y sin esto el orden lo decidiría el planificador.
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Verificada contra `raw_text` por `rules.py`: el modelo no puede
    # fabricar una cita que no esté en el anuncio.
    source_quote: Mapped[str] = mapped_column(sa.Text, nullable=False)
    kind: Mapped[vocab.RequirementKind] = mapped_column(
        vocabulary(vocab.RequirementKind, "requirement_kind"), nullable=False
    )
    category: Mapped[vocab.RequirementCategory] = mapped_column(
        vocabulary(vocab.RequirementCategory, "requirement_category"), nullable=False
    )
    match: Mapped[vocab.RequirementMatch | None] = mapped_column(
        vocabulary(vocab.RequirementMatch, "requirement_match"), nullable=True
    )
    evidence_ref: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cv_action: Mapped[vocab.CvAction | None] = mapped_column(
        vocabulary(vocab.CvAction, "cv_action"), nullable=True
    )

    extraction: Mapped[OfferExtraction] = relationship(back_populates="requirements")


class OfferAnomaly(Base):
    """Requisitos imposibles o mal configurados, con su explicación.

    Ni se cumplen ni se ignoran: se registran, porque en M2 pueden activar un
    filtro automático. `requirement_id` es nullable porque una anomalía puede
    ser del anuncio entero y no de un requisito concreto.
    """

    __tablename__ = "offer_anomalies"
    __table_args__ = (sa.UniqueConstraint("extraction_id", "position"),)

    id: Mapped[UuidPk]
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("offer_extractions.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("offer_requirements.id", ondelete="CASCADE"), nullable=True
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    explanation: Mapped[str] = mapped_column(sa.Text, nullable=False)
    source_quote: Mapped[str] = mapped_column(sa.Text, nullable=False)

    extraction: Mapped[OfferExtraction] = relationship(back_populates="anomalies")
    # El requisito que explica esta anomalía, cuando la anomalía es de un
    # requisito concreto y no del anuncio entero.
    requirement: Mapped[OfferRequirement | None] = relationship(lazy="selectin")
