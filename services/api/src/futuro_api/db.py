"""Acceso a Postgres.

M0 no define todavía ninguna tabla: lo único que hace falta es un motor con
pool y una comprobación de conectividad para `/api/health`. Las tablas del
contrato de oferta llegan en M1, ya con Alembic.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa común; Alembic la usa como metadata objetivo."""


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
