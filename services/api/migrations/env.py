"""Entorno de Alembic.

`futuro_api.models` se importa aquí, aunque no se use en este fichero,
porque `Base.metadata` solo conoce las tablas de los módulos que alguien ha
importado. Sin esa línea, `--autogenerate` propondría borrar el esquema
entero y `alembic check` diría que todo está en orden.
"""

from __future__ import annotations

import asyncio
from typing import Any

from alembic import context
from sqlalchemy import CheckConstraint, Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import futuro_api.models  # noqa: F401  (puebla Base.metadata con todo)
from futuro_api.config import get_settings
from futuro_api.db import Base

config = context.config
target_metadata = Base.metadata
database_url = get_settings().database_url


def _type_bound_check_names() -> frozenset[str]:
    """Nombres de los CHECK que genera `sa.Enum(create_constraint=True)`.

    Alembic los excluye a propósito del lado del metadata —los considera
    gestionados por el tipo de la columna— pero sí los reflecta del lado de
    la base de datos. Sin filtrarlos, `--autogenerate` propone borrar los
    dieciocho en cada revisión y `alembic check` nunca está limpio.

    `_type_bound` es un atributo privado de SQLAlchemy, pero es exactamente
    el criterio que usa Alembic por dentro, así que preguntar por otra cosa
    sería adivinar.
    """
    return frozenset(
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
        and getattr(constraint, "_type_bound", False)
        and constraint.name is not None
    )


TYPE_BOUND_CHECKS = _type_bound_check_names()


def include_name(
    name: str | None, type_: str, parent_names: dict[str, str | None]
) -> bool:
    """Deja fuera de la comparación los CHECK de vocabulario.

    El precio de este filtro es que ampliar un vocabulario deja de aparecer
    como deriva de esquema. Lo cubre `tests/test_schema.py`, que compara
    cada CHECK real de la base de datos contra su `StrEnum`: es más preciso
    que autogenerate, porque mira los valores y no solo la existencia de la
    constraint.
    """
    if type_ == "check_constraint":
        return name not in TYPE_BOUND_CHECKS
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    section: dict[str, Any] = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = database_url
    engine = async_engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
