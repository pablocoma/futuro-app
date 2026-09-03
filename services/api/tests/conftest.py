"""Fixtures de la API.

Los tests de la aplicación no necesitan Postgres: `/api/health` degrada a
`unreachable` cuando la base no responde, y ese es justamente uno de los
casos que hay que cubrir; el caso `ok` se cubre sustituyendo el ping.

Los tests de esquema sí lo necesitan, porque lo que comprueban son
constraints y triggers de Postgres, que no existen en ninguna otra parte.
Usan una base aparte, `futuro_test`, recreada desde cero en cada sesión.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from futuro_api import db
from futuro_api.config import Settings
from futuro_api.main import create_app

TEST_DATABASE = "futuro_test"
API_ROOT = Path(__file__).resolve().parent.parent

ALLOWED = "allowed@example.test"


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "env": "development",
        "session_secret": "test-secret",
        "google_client_id": "test-client-id",
        "google_client_secret": "test-client-secret",
        "allowed_emails": ALLOWED,
        "postgres_host": "127.0.0.1",
        "postgres_port": 1,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def make_production_settings(**overrides: object) -> Settings:
    """Unos ajustes de producción que sí arrancan.

    Producción exige más que desarrollo, y la lista crece: credenciales de
    OAuth, un secreto de sesión propio, HTTPS y, desde M1, un proveedor de
    LLM real con un modelo de tarifa conocida. Tenerla en un solo sitio
    evita que cada test que necesita un `ENV=production` válido se rompa
    cada vez que se añade un requisito nuevo.
    """
    base: dict[str, object] = {
        "env": "production",
        "session_secret": "a-real-secret",
        "public_base_url": "https://example.test",
        "llm_provider": "openai",
        "openai_api_key": "sk-inventada",
        "openai_model": "gpt-5.6-terra",
    }
    base.update(overrides)
    return make_settings(**base)


def make_app(**overrides: object) -> FastAPI:
    return create_app(make_settings(**overrides))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(make_app()) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Base de datos real, solo para los tests de esquema
# ---------------------------------------------------------------------------


def _postgres_settings(database: str) -> Settings:
    """Ajustes apuntando a `database`, leyendo el entorno.

    El valor por defecto es `localhost` y no el `postgres` de la
    aplicación: los tests corren fuera de Compose, contra el puerto que el
    override expone al Mac. En CI llega por `POSTGRES_HOST`.
    """
    return Settings(
        postgres_host=os.environ.get("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_db=database,
        postgres_user=os.environ.get("POSTGRES_USER", "futuro"),
        postgres_password=os.environ.get("POSTGRES_PASSWORD", "futuro"),
    )


async def _recreate_database() -> None:
    """Tira y vuelve a crear `futuro_test` desde la base de mantenimiento."""
    admin = db.create_engine(_postgres_settings("postgres").database_url)
    try:
        async with admin.connect() as connection:
            # Cada sesión de tests empieza sin nada: un esquema arrastrado de
            # una ejecución anterior haría pasar tests que no deberían pasar.
            await connection.execution_options(isolation_level="AUTOCOMMIT")
            await connection.execute(
                sa.text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)')
            )
            await connection.execute(sa.text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """URL de una base recién creada y migrada con Alembic.

    Se ejecuta `alembic upgrade head` en un subproceso, y no
    `Base.metadata.create_all()`, por dos razones. La primera es que lo que
    hay que probar es la migración que corre el deploy y no una versión
    paralela del esquema generada desde los modelos. La segunda es concreta:
    `create_all` no instala el trigger de inmutabilidad, así que los tests
    pasarían en verde sobre un esquema que no existe en ningún sitio.

    Si Postgres no contesta, el fallo es explícito: un harness que se salta
    los tests en silencio es peor que uno que falla.
    """
    settings = _postgres_settings(TEST_DATABASE)
    try:
        asyncio.run(_recreate_database())
    except OSError as error:  # pragma: no cover - depende del entorno
        pytest.fail(
            f"no hay Postgres en {settings.postgres_host}:{settings.postgres_port} "
            f"({error}). En local: `make up`.",
            pytrace=False,
        )
    # Al subproceso se le pasan los cuatro valores ya resueltos y no solo el
    # nombre de la base: si heredara el resto del entorno, `env.py` volvería
    # a leer los valores por defecto de la aplicación y migraría —o
    # intentaría migrar— una base distinta de la que se acaba de crear.
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        env={
            **os.environ,
            "POSTGRES_HOST": settings.postgres_host,
            "POSTGRES_PORT": str(settings.postgres_port),
            "POSTGRES_DB": settings.postgres_db,
            "POSTGRES_USER": settings.postgres_user,
            "POSTGRES_PASSWORD": settings.postgres_password,
        },
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # pragma: no cover - solo si la migración rompe
        pytest.fail(f"`alembic upgrade head` falló:\n{result.stderr}", pytrace=False)
    return settings.database_url


@pytest.fixture
async def connection(migrated_database: str) -> AsyncIterator[AsyncConnection]:
    """Conexión a la base migrada, en una transacción que siempre se deshace.

    Cada test acaba con un `rollback`, así que no hay que truncar nada ni
    importa el orden en que se ejecuten.
    """
    engine = db.create_engine(migrated_database)
    try:
        async with engine.connect() as open_connection:
            transaction = await open_connection.begin()
            try:
                yield open_connection
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def session(connection: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """Sesión atada a la conexión del test, que siempre se deshace.

    Sirve para lo que no commitea: el repositorio hace `flush` y deja la
    frontera de la transacción a quien llama, así que dentro de un test se
    puede escribir, leer y descartarlo todo al terminar.
    """
    async with AsyncSession(bind=connection, expire_on_commit=False) as open_session:
        yield open_session


@pytest.fixture
async def sessions(
    migrated_database: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Una fábrica de sesiones de verdad, con limpieza al terminar.

    La tarea del worker abre y cierra sus propias sesiones y commitea varias
    veces —el coste de la llamada se guarda aparte de la extracción, a
    propósito— así que no se puede probar dentro de una transacción que se
    deshace: hay que dejarla commitear y limpiar después. Probar la
    estructura real de sus transacciones es parte de lo que interesa.

    No mezclar con la fixture `session` en el mismo test: son conexiones
    distintas, y lo que una no ha commiteado la otra no lo ve.
    """
    engine = db.create_engine(migrated_database)
    try:
        yield db.create_session_factory(engine)
    finally:
        async with engine.begin() as connection:
            # `CASCADE` alcanza las tablas que las referencian, así que esto
            # vacía también extracciones, requisitos, anomalías y llamadas.
            await connection.execute(
                sa.text(
                    "TRUNCATE offer_captures, companies, job_runs "
                    "RESTART IDENTITY CASCADE"
                )
            )
        await engine.dispose()
