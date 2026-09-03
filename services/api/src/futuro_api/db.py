"""Acceso a Postgres.

Las tablas del contrato de oferta viven en `futuro_api.offers.models` y las
de trabajos en `futuro_api.jobs.models`; aquí solo está la maquinaria común:
la base declarativa, el motor con pool y la comprobación de conectividad de
`/api/health`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from enum import StrEnum
from typing import Annotated

import sqlalchemy as sa
from sqlalchemy import Enum as SaEnum
from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Nombres deterministas para índices y constraints. Tiene que estar aquí
# ANTES de la primera migración: sin esta convención, Alembic autogenera
# nombres que dependen del backend, y un `downgrade` que tiene que borrar
# una constraint por su nombre se vuelve frágil. El rollback del deploy no
# revierte esquema, así que la reversibilidad se prueba en CI y necesita que
# los nombres sean estables.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


def vocabulary(values: type[StrEnum], name: str) -> SaEnum:
    """Columna de vocabulario cerrado: VARCHAR con CHECK, no un enum nativo.

    `native_enum=False` a propósito. Un enum nativo de Postgres obliga a
    `ALTER TYPE ... ADD VALUE` para crecer, que no se puede usar en la misma
    transacción que lo necesita y no tiene forma de quitar un valor; con
    VARCHAR y CHECK, ampliar un vocabulario es cambiar una constraint en una
    migración, y eso sí es reversible. La validación de verdad está en
    Pydantic, antes de llegar aquí; esto es la red de debajo.

    `values_callable` para persistir el valor (`"ai_engineer"`) y no el
    nombre del miembro (`"AI_ENGINEER"`), que es lo que SQLAlchemy haría por
    defecto y no es lo que dice el contrato.
    """
    return SaEnum(
        values,
        name=name,
        native_enum=False,
        # Explícito porque el valor por defecto es `False` desde SQLAlchemy
        # 1.4: sin esto la columna es un VARCHAR pelado que acepta cualquier
        # cadena, y la "red de debajo" de este docstring no existiría. Se
        # descubrió metiendo un canal inventado con psql y viendo que entraba.
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda enum_type: [member.value for member in enum_type],
    )


# Tipos anotados compartidos por todos los modelos. La clave primaria
# lleva las dos formas de generar el UUID a propósito: `default` para que lo
# ponga Python —que es lo que permite conocer el id antes del flush— y
# `server_default` para que el esquema sea usable desde SQL a pelo, en una
# migración de datos o en una sesión de psql. Sin el segundo, cualquier
# INSERT que no venga del ORM falla por `id` nulo.
UuidPk = Annotated[
    uuid.UUID,
    mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    ),
]

CreatedAt = Annotated[
    datetime,
    mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
]


class Base(DeclarativeBase):
    """Base declarativa común; Alembic la usa como metadata objetivo."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine(database_url: str) -> AsyncEngine:
    return _create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


async def ping(engine: AsyncEngine) -> None:
    """Lanza si la base de datos no responde."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
