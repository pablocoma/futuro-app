"""Puntuacion y recomendacion de variante: la capa assessment del contrato

Revision ID: 0002
Revises: 0001

La tercera capa del contrato de datos, y la primera mutable en el sentido de
que se puede volver a calcular. «Recalculable» no significa editable: las
cinco tablas de aqui llevan el mismo trigger `BEFORE UPDATE` que las dos
capas de la migracion 0001, y repuntuar es insertar una fila nueva. Sin el
trigger, alguien arregla una nota en sitio y la promesa de que dos ofertas
puntuadas con modelos de scoring distintos se noten muere en silencio.

Compatible hacia atras: solo crea tablas y amplia un vocabulario. Nada de
0001 cambia de forma, asi que la version anterior de la aplicacion sigue
funcionando contra este esquema, que es lo que exige el rollback del deploy
—vuelve al tag de imagen anterior y no revierte migraciones—.

El `downgrade` tiene un paso que no es simetrico y esta comentado abajo:
estrechar el vocabulario de `job_runs.kind` obliga a borrar antes las filas
de los trabajos de puntuacion, porque si no violarian el CHECK que se
repone.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Las tablas nuevas que no admiten UPDATE. Una sola lista para instalar y
# para quitar, igual que en 0001: si divergieran, un `downgrade` dejaria
# triggers huerfanos.
_IMMUTABLE_TABLES = (
    "offer_assessments",
    "offer_assessment_dimensions",
    "offer_assessment_gates",
    "offer_requirement_matches",
    "offer_variant_recommendations",
)

# El vocabulario de `job_runs.kind`, antes y despues. Escrito a mano y no
# leido de `JobKind`: una migracion es una foto de un momento, y si siguiera
# al enum, la de hoy cambiaria de significado cuando alguien anada un tipo
# de trabajo en el futuro.
_JOB_KINDS_BEFORE = ("offer_extraction",)
_JOB_KINDS_AFTER = ("offer_extraction", "offer_assessment")


def _job_kind_check(values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"CHECK (kind IN ({listed}))"


def upgrade() -> None:
    _widen_job_kinds()
    op.create_table(
        "offer_assessments",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("job_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "llm",
                "recomputed",
                name="assessment_source",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("derived_from_id", sa.Uuid(), nullable=True),
        sa.Column("scoring_model_version", sa.Text(), nullable=False),
        sa.Column("scoring_model_sha256", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("value_score", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("coverage", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column(
            "probability_band",
            sa.Enum(
                "high",
                "medium",
                "low",
                "very_low",
                name="probability_band",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("probability_reason", sa.Text(), nullable=False),
        sa.Column(
            "portfolio_bucket",
            sa.Enum(
                "realistic",
                "realistic_stretch",
                "aspirational",
                "experimental",
                "discard",
                name="portfolio_bucket",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
        ),
        sa.Column("portfolio_note", sa.Text(), nullable=True),
        sa.Column(
            "effort_tier",
            sa.Enum(
                "full",
                "standard",
                "cheap",
                "skip",
                name="effort_tier",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "corrections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "assessed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(source = 'llm') = (prompt_version IS NOT NULL AND model IS NOT NULL)",
            name=op.f("ck_offer_assessments_llm_declares_prompt_and_model"),
        ),
        sa.CheckConstraint(
            "source <> 'recomputed' OR derived_from_id IS NOT NULL",
            name=op.f("ck_offer_assessments_recomputed_declares_its_origin"),
        ),
        sa.CheckConstraint(
            "source <> 'recomputed' OR job_run_id IS NULL",
            name=op.f("ck_offer_assessments_recomputed_has_no_job"),
        ),
        sa.CheckConstraint(
            "coverage >= 0 AND coverage <= 1",
            name=op.f("ck_offer_assessments_coverage_is_a_fraction"),
        ),
        sa.CheckConstraint(
            "portfolio_bucket IS NOT NULL OR portfolio_note IS NOT NULL",
            name=op.f("ck_offer_assessments_missing_bucket_explains_itself"),
        ),
        sa.CheckConstraint(
            "value_score IS NULL OR (value_score >= 0 AND value_score <= 5)",
            name=op.f("ck_offer_assessments_value_score_in_scale"),
        ),
        sa.ForeignKeyConstraint(
            ["derived_from_id"],
            ["offer_assessments.id"],
            name=op.f("fk_offer_assessments_derived_from_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["offer_extractions.id"],
            name=op.f("fk_offer_assessments_extraction_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_run_id"],
            ["job_runs.id"],
            name=op.f("fk_offer_assessments_job_run_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_assessments")),
        sa.UniqueConstraint("job_run_id", name=op.f("uq_offer_assessments_job_run_id")),
    )
    op.create_index(
        "ix_offer_assessments_extraction_id_assessed_at",
        "offer_assessments",
        ["extraction_id", sa.literal_column("assessed_at DESC")],
        unique=False,
    )
    op.create_table(
        "offer_variant_recommendations",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("extraction_id", sa.Uuid(), nullable=False),
        sa.Column("job_run_id", sa.Uuid(), nullable=True),
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column(
            "confidence",
            sa.Enum(
                "high",
                "medium",
                "low",
                name="confidence",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("variants_guide_sha256", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "recommended_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["offer_extractions.id"],
            name=op.f("fk_offer_variant_recommendations_extraction_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_run_id"],
            ["job_runs.id"],
            name=op.f("fk_offer_variant_recommendations_job_run_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_variant_recommendations")),
        sa.UniqueConstraint(
            "job_run_id", name=op.f("uq_offer_variant_recommendations_job_run_id")
        ),
    )
    op.create_index(
        "ix_offer_variant_recommendations_extraction_id_recommended_at",
        "offer_variant_recommendations",
        ["extraction_id", sa.literal_column("recommended_at DESC")],
        unique=False,
    )
    op.create_table(
        "offer_assessment_dimensions",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("anchor", sa.Text(), nullable=True),
        sa.Column("unscored_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(score IS NULL) = (unscored_reason IS NOT NULL)",
            name=op.f("ck_offer_assessment_dimensions_unscored_explains_itself"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 5)",
            name=op.f("ck_offer_assessment_dimensions_score_in_scale"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR citation IS NOT NULL",
            name=op.f("ck_offer_assessment_dimensions_score_needs_citation"),
        ),
        sa.CheckConstraint(
            "weight > 0", name=op.f("ck_offer_assessment_dimensions_weight_positive")
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["offer_assessments.id"],
            name=op.f("fk_offer_assessment_dimensions_assessment_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_assessment_dimensions")),
        sa.UniqueConstraint(
            "assessment_id",
            "dimension",
            name=op.f("uq_offer_assessment_dimensions_assessment_id_dimension"),
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "position",
            name=op.f("uq_offer_assessment_dimensions_assessment_id_position"),
        ),
    )
    op.create_table(
        "offer_assessment_gates",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("gate", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pass",
                "stretch",
                "pending",
                "fail",
                name="gate_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(status = 'pending') = (citation IS NULL)",
            name=op.f("ck_offer_assessment_gates_only_a_decided_gate_cites"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["offer_assessments.id"],
            name=op.f("fk_offer_assessment_gates_assessment_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_assessment_gates")),
        sa.UniqueConstraint(
            "assessment_id",
            "gate",
            name=op.f("uq_offer_assessment_gates_assessment_id_gate"),
        ),
        sa.UniqueConstraint(
            "assessment_id",
            "position",
            name=op.f("uq_offer_assessment_gates_assessment_id_position"),
        ),
    )
    op.create_table(
        "offer_requirement_matches",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
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
            nullable=False,
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
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "match <> 'meets' OR evidence_ref IS NOT NULL",
            name=op.f("ck_offer_requirement_matches_meets_needs_evidence_ref"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["offer_assessments.id"],
            name=op.f("fk_offer_requirement_matches_assessment_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["offer_requirements.id"],
            name=op.f("fk_offer_requirement_matches_requirement_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_requirement_matches")),
        sa.UniqueConstraint(
            "assessment_id",
            "requirement_id",
            name=op.f("uq_offer_requirement_matches_assessment_id_requirement_id"),
        ),
    )
    _install_immutability()


def downgrade() -> None:
    _remove_immutability()
    op.drop_table("offer_requirement_matches")
    op.drop_table("offer_assessment_gates")
    op.drop_table("offer_assessment_dimensions")
    op.drop_index(
        "ix_offer_variant_recommendations_extraction_id_recommended_at",
        table_name="offer_variant_recommendations",
    )
    op.drop_table("offer_variant_recommendations")
    op.drop_index(
        "ix_offer_assessments_extraction_id_assessed_at", table_name="offer_assessments"
    )
    op.drop_table("offer_assessments")
    _narrow_job_kinds()


def _widen_job_kinds() -> None:
    """Amplia el vocabulario de `job_runs.kind` con el trabajo de puntuacion.

    Va escrito a mano y no lo propone `--autogenerate`: los CHECK que genera
    `sa.Enum(create_constraint=True)` estan fuera de la comparacion de
    Alembic por el filtro `include_name` de `migrations/env.py`. Lo que si
    lo vigila es `tests/test_schema.py`, que compara los valores del CHECK
    real contra el `StrEnum`, asi que olvidarse de esto rompe el harness.

    Cambiar una constraint es reversible, que es exactamente por lo que 0001
    eligio VARCHAR con CHECK en vez de un enum nativo de Postgres: un
    `ALTER TYPE ... ADD VALUE` no se puede usar en la misma transaccion que
    lo necesita y no tiene inverso.
    """
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        + _job_kind_check(_JOB_KINDS_AFTER)
    )


def _narrow_job_kinds() -> None:
    """Repone el vocabulario de un solo tipo de trabajo.

    Borra antes las filas de los trabajos de puntuacion, y eso es perdida de
    datos en un `downgrade`, asi que conviene que este dicho: sin ese
    DELETE, el CHECK que se repone lo violarian las filas existentes y la
    migracion no bajaria. Es aceptable porque lo que esas filas registran
    —la ejecucion de un trabajo de puntuacion— apunta a tablas que este
    mismo `downgrade` esta borrando. `llm_calls` se va con ellas por la
    clave ajena en cascada.
    """
    op.execute("DELETE FROM job_runs WHERE kind = 'offer_assessment'")
    op.execute("ALTER TABLE job_runs DROP CONSTRAINT ck_job_runs_job_kind")
    op.execute(
        "ALTER TABLE job_runs ADD CONSTRAINT ck_job_runs_job_kind "
        + _job_kind_check(_JOB_KINDS_BEFORE)
    )


def _install_immutability() -> None:
    """Extiende a la capa nueva el trigger que 0001 dejo instalado.

    La funcion `futuro_raise_immutable()` ya existe desde 0001; aqui solo se
    cuelgan los triggers. El DDL no queda afectado, asi que anadir columnas
    sigue siendo libre; lo que queda bloqueado es rellenarlas, y un backfill
    futuro tendra que quitar y reponer el trigger en su propia migracion,
    que es la decision explicita que se quiere forzar.
    """
    for table in _IMMUTABLE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION futuro_raise_immutable()
            """
        )


def _remove_immutability() -> None:
    for table in _IMMUTABLE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
