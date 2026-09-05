"""Guardar y leer el dossier mínimo.

Igual que el resto de repositorios de la aplicación: ninguna función de aquí
hace `commit` -la frontera de la transacción la decide quien llama- ni valida
nada -eso ya pasó en el router, contra el repositorio de datos cargado en ese
momento-.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.models import Application


async def create_application(
    session: AsyncSession,
    *,
    capture_id: uuid.UUID,
    recommendation_id: uuid.UUID | None,
    variant: str,
    cv_sha256: str,
) -> Application:
    application = Application(
        capture_id=capture_id,
        recommendation_id=recommendation_id,
        variant=variant,
        cv_sha256=cv_sha256,
    )
    session.add(application)
    await session.flush()
    return application


async def current_application(
    session: AsyncSession, capture_id: uuid.UUID
) -> Application | None:
    """El dossier vigente de una oferta: el último, por si cambió de variante."""
    return (
        await session.execute(
            sa.select(Application)
            .where(Application.capture_id == capture_id)
            .order_by(Application.confirmed_at.desc(), Application.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
