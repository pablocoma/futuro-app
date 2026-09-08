"""Estado de candidatura: la linea de tiempo del pipeline

Revision ID: 0004
Revises: 0003

Tabla nueva, `offer_status_events`, hermana de `applications` y no una
columna anadida sobre ella: el estado (`research`/`preparing`/`submitted`/
`interview`/`closed`) empieza antes de que exista ninguna variante
confirmada, y `applications.variant`/`cv_sha256` son NOT NULL desde 0003.
Meter las dos cosas en una tabla habria exigido hacerlos nullable y
mezclar dos eventos distintos -cambiar de variante, cambiar de etapa- en
una sola fila. Es una desviacion de lo que el docstring de 0003 anticipaba
("ALTER TABLE aditivo sobre `applications`"): esa era una nota de
intencion de Fase 1, no una decision cerrada de arquitectura. Detalle
completo en `docs/decisions/fase-3-estados-de-candidatura.md`.

Cuelga de `capture_id`, igual que `applications`. Append-only con el mismo
trigger de inmutabilidad -cambiar de etapa es una fila nueva, no un
`UPDATE`-, y "vigente" es la ultima por `(occurred_at DESC, id DESC)`. Sin
orden de transicion forzado: la base de datos no impone una maquina de
estados.

Compatible hacia atras: solo crea una tabla. Nada de 0001-0003 cambia de
forma.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IMMUTABLE_TABLES = ("offer_status_events",)


def upgrade() -> None:
    op.create_table(
        "offer_status_events",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "research",
                "preparing",
                "submitted",
                "interview",
                "closed",
                name="application_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["capture_id"],
            ["offer_captures.id"],
            name=op.f("fk_offer_status_events_capture_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer_status_events")),
    )
    op.create_index(
        "ix_offer_status_events_capture_id_occurred_at",
        "offer_status_events",
        ["capture_id", sa.literal_column("occurred_at DESC")],
        unique=False,
    )
    _install_immutability()


def downgrade() -> None:
    _remove_immutability()
    op.drop_index(
        "ix_offer_status_events_capture_id_occurred_at",
        table_name="offer_status_events",
    )
    op.drop_table("offer_status_events")


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
