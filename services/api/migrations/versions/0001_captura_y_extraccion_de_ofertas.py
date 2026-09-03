"""Captura y extracción de ofertas: las primeras tablas.

Las capas `capture` y `extraction` del contrato de datos
(`Futuro/docs/OFFER_DATA_CONTRACT.md`), más la mitad operativa que hacía
falta para producirlas: `job_runs` y `llm_calls`. La capa `assessment` no
está: es M2.

Además de las tablas, instala el trigger que hace inmutables las dos capas
del contrato; la nota está al final de `upgrade()`.

Revision ID: 0001
Revises:
Create Date: 2026-09-03 23:16:52.379200
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Las tablas que no admiten UPDATE. Una sola lista para instalar y para
# quitar: si divergieran, un `downgrade` dejaría triggers huérfanos.
_IMMUTABLE_TABLES = (
    "offer_captures",
    "offer_extractions",
    "offer_requirements",
    "offer_anomalies",
)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("name_key", name=op.f("uq_companies_name_key")),
    )
    op.create_table(
        "offer_captures",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "source",
            sa.Enum(
                "paste",
                "url",
                "extension",
                "telegram",
                "email",
                name="source_channel",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_text_sha256", sa.String(length=64), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("capture_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(raw_text) > 0", name=op.f("ck_offer_captures_raw_text_not_empty")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_captures")),
        sa.UniqueConstraint(
            "raw_text_sha256", name=op.f("uq_offer_captures_raw_text_sha256")
        ),
    )
    op.create_index(
        "ix_offer_captures_captured_at",
        "offer_captures",
        [sa.literal_column("captured_at DESC")],
        unique=False,
    )
    op.create_table(
        "job_runs",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "offer_extraction",
                name="job_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                name="job_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("capture_id", sa.Uuid(), nullable=True),
        sa.Column("arq_job_id", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("attempt >= 1", name=op.f("ck_job_runs_attempt_positive")),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["offer_captures.id"],
            name=op.f("fk_job_runs_capture_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_runs")),
        sa.UniqueConstraint("arq_job_id", name=op.f("uq_job_runs_arq_job_id")),
    )
    op.create_index(
        "ix_job_runs_status_queued_at",
        "job_runs",
        ["status", "queued_at"],
        unique=False,
    )
    op.create_table(
        "llm_calls",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("job_run_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "cached_input_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("pricing_version", sa.Text(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "succeeded",
                "failed",
                "refused",
                name="llm_call_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cost_usd >= 0", name=op.f("ck_llm_calls_cost_not_negative")
        ),
        sa.CheckConstraint(
            "latency_ms >= 0", name=op.f("ck_llm_calls_latency_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["job_run_id"],
            ["job_runs.id"],
            name=op.f("fk_llm_calls_job_run_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_table(
        "offer_extractions",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("job_run_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "corrections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "role_family",
            sa.Enum(
                "ai_engineer",
                "machine_learning_engineer",
                "data_scientist",
                "data_ai_consultant",
                "solutions_engineer",
                "forward_deployed_engineer",
                "data_engineer",
                "quantitative_roles",
                "other",
                name="role_family",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "seniority_label",
            sa.Enum(
                "junior",
                "mid",
                "senior",
                "staff",
                "lead",
                "unspecified",
                name="seniority_label",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "experience_years_required", sa.Numeric(precision=4, scale=1), nullable=True
        ),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column(
            "work_mode",
            sa.Enum(
                "onsite",
                "hybrid",
                "remote",
                name="work_mode",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("hiring_regions", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("language_of_work", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "contract_vehicle",
            sa.Enum(
                "employment",
                "eor",
                "b2b",
                "unknown",
                name="contract_vehicle",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "posting_status",
            sa.Enum(
                "active_verified",
                "expired",
                "unverifiable",
                name="posting_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("status_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "responsibilities",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("posting_company_id", sa.Uuid(), nullable=True),
        sa.Column("employer_company_id", sa.Uuid(), nullable=True),
        sa.Column(
            "employer_confidence",
            sa.Enum(
                "confirmed",
                "high",
                "medium",
                "low",
                name="employer_confidence",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("comp_amount_min", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("comp_amount_max", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("comp_currency", sa.String(length=3), nullable=True),
        sa.Column(
            "comp_period",
            sa.Enum(
                "year",
                "month",
                "day",
                "hour",
                "unclear",
                name="compensation_period",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column(
            "comp_basis",
            sa.Enum(
                "base",
                "total",
                "unclear",
                name="compensation_basis",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("comp_bonus_pct", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column(
            "comp_bonus_type",
            sa.Enum(
                "target",
                "max",
                "discretionary",
                "unclear",
                name="bonus_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("comp_equity", sa.Text(), nullable=True),
        sa.Column(
            "comp_territorial_adjustment",
            sa.Enum(
                "localised",
                "not_localised",
                "unclear",
                name="territorial_adjustment",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "posting_status <> 'active_verified' OR status_checked_at IS NOT NULL",
            name=op.f("ck_offer_extractions_active_verified_needs_checked_at"),
        ),
        sa.CheckConstraint(
            "employer_company_id IS NULL OR employer_confidence IS NOT NULL",
            name=op.f("ck_offer_extractions_employer_needs_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["offer_captures.id"],
            name=op.f("fk_offer_extractions_capture_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employer_company_id"],
            ["companies.id"],
            name=op.f("fk_offer_extractions_employer_company_id"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["job_run_id"],
            ["job_runs.id"],
            name=op.f("fk_offer_extractions_job_run_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["posting_company_id"],
            ["companies.id"],
            name=op.f("fk_offer_extractions_posting_company_id"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_extractions")),
        sa.UniqueConstraint("job_run_id", name=op.f("uq_offer_extractions_job_run_id")),
    )
    op.create_index(
        "ix_offer_extractions_capture_id_extracted_at",
        "offer_extractions",
        ["capture_id", sa.literal_column("extracted_at DESC")],
        unique=False,
    )
    op.create_table(
        "offer_requirements",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "mandatory",
                "desirable",
                "anomalous",
                name="requirement_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "technology",
                "experience_years",
                "domain",
                "autonomy",
                "language",
                "education",
                "other",
                name="requirement_category",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "match",
            sa.Enum(
                "meets",
                "partial",
                "no_evidence",
                name="requirement_match",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("evidence_ref", sa.Text(), nullable=True),
        sa.Column(
            "cv_action",
            sa.Enum(
                "include",
                "prioritise",
                "omit",
                name="cv_action",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.CheckConstraint(
            "match <> 'meets' OR evidence_ref IS NOT NULL",
            name=op.f("ck_offer_requirements_meets_needs_evidence_ref"),
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["offer_extractions.id"],
            name=op.f("fk_offer_requirements_extraction_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_requirements")),
        sa.UniqueConstraint(
            "extraction_id",
            "position",
            name=op.f("uq_offer_requirements_extraction_id_position"),
        ),
    )
    op.create_table(
        "offer_anomalies",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["offer_extractions.id"],
            name=op.f("fk_offer_anomalies_extraction_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["offer_requirements.id"],
            name=op.f("fk_offer_anomalies_requirement_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_anomalies")),
        sa.UniqueConstraint(
            "extraction_id",
            "position",
            name=op.f("uq_offer_anomalies_extraction_id_position"),
        ),
    )

    # Inmutabilidad impuesta por la base de datos, no por convención. Las dos
    # capas del contrato son inmutables y sus hijas lo son con ellas.
    # `job_runs` y `llm_calls` NO llevan trigger: un job cambia de estado y no
    # es una capa del contrato.
    #
    # El DDL no queda afectado —un ALTER TABLE no es un UPDATE—, así que
    # añadir columnas sigue siendo libre. Lo que queda bloqueado es rellenar
    # esas columnas: un backfill futuro tendrá que quitar y reponer el trigger
    # dentro de su propia migración, que es justo la decisión explícita que se
    # quiere forzar.
    op.execute(
        """
        CREATE FUNCTION futuro_raise_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'la tabla % es inmutable: % no esta permitido',
                TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$
        """
    )
    for table in _IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION futuro_raise_immutable()
            """
        )


def downgrade() -> None:
    # Primero los triggers: si no, el propio downgrade no podría tocar nada.
    for table in _IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS futuro_raise_immutable()")
    op.drop_table("offer_anomalies")
    op.drop_table("offer_requirements")
    op.drop_index(
        "ix_offer_extractions_capture_id_extracted_at", table_name="offer_extractions"
    )
    op.drop_table("offer_extractions")
    op.drop_table("llm_calls")
    op.drop_index("ix_job_runs_status_queued_at", table_name="job_runs")
    op.drop_table("job_runs")
    op.drop_index("ix_offer_captures_captured_at", table_name="offer_captures")
    op.drop_table("offer_captures")
    op.drop_table("companies")
