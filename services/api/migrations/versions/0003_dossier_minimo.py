"""Dossier minimo: que variante confirmo Pablo, y con que PDF

Revision ID: 0003
Revises: 0002

Una sola tabla, `applications`. Cuelga de `offer_captures` y no de la
extraccion ni del assessment: confirmar una variante es un gesto sobre *la
oferta*, el mismo principio que ya usa `job_runs.capture_id`. Lleva el mismo
trigger de inmutabilidad que las demas capas -cambiar de variante es una
fila nueva, no un `UPDATE`- y una referencia opcional, `SET NULL`, a la
recomendacion que confirmo o descarto.

`docs/OFFER_DATA_CONTRACT.md` (repositorio privado) ya reserva el nombre
`applications` para la candidatura completa, con `status`, `channel`,
`submitted_at`, `follow_up_at`, `outcome` e interacciones. Esas columnas son
Fase 3 y entraran con un `ALTER TABLE` aditivo sobre esta misma tabla, no con
un renombrado: es la misma disciplina de migraciones compatibles hacia atras
que ya sigue el resto del esquema.

Compatible hacia atras: solo crea una tabla. Nada de 0001 ni 0002 cambia de
forma.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Una sola tabla hoy, pero la misma lista que 0001 y 0002 usan para instalar
# y quitar el trigger: si algun dia esta migracion gana una tabla hermana,
# el patron ya esta puesto.
_IMMUTABLE_TABLES = ("applications",)


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column("cv_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["offer_captures.id"],
            name=op.f("fk_applications_capture_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["offer_variant_recommendations.id"],
            name=op.f("fk_applications_recommendation_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
    )
    op.create_index(
        "ix_applications_capture_id_confirmed_at",
        "applications",
        ["capture_id", sa.literal_column("confirmed_at DESC")],
        unique=False,
    )
    _install_immutability()


def downgrade() -> None:
    _remove_immutability()
    op.drop_index("ix_applications_capture_id_confirmed_at", table_name="applications")
    op.drop_table("applications")


def _install_immutability() -> None:
    """Cuelga el trigger que 0001 dejo instalado; la funcion ya existe."""
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
