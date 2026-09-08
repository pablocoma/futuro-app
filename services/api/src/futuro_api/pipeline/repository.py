"""Guardar y leer la línea de tiempo del estado de una candidatura.

Igual que el resto de repositorios de la aplicación: ninguna función de aquí
hace `commit` -la frontera de la transacción la decide quien llama- ni valida
nada -el router ya comprobó que la oferta existe antes de llamar-.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.pipeline.models import OfferStatusEvent
from futuro_api.pipeline.vocabularies import DEFAULT_STATUS, ApplicationStatus


async def record_status(
    session: AsyncSession, *, capture_id: uuid.UUID, status: ApplicationStatus
) -> OfferStatusEvent:
    event = OfferStatusEvent(capture_id=capture_id, status=status)
    session.add(event)
    await session.flush()
    return event


async def current_status_event(
    session: AsyncSession, capture_id: uuid.UUID
) -> OfferStatusEvent | None:
    """El evento vigente: el último, por si cambió de etapa."""
    return (
        await session.execute(
            sa.select(OfferStatusEvent)
            .where(OfferStatusEvent.capture_id == capture_id)
            .order_by(OfferStatusEvent.occurred_at.desc(), OfferStatusEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def current_status(
    session: AsyncSession, capture_id: uuid.UUID
) -> ApplicationStatus:
    """El estado vigente, o `research` si todavía no se ha registrado ninguno.

    No se escribe una fila al capturar: `research` es el valor implícito de
    "sin decidir todavía", y escribirlo de oficio en cada ingesta ensuciaría
    la línea de tiempo con una transición que nadie pidió.
    """
    event = await current_status_event(session, capture_id)
    return event.status if event is not None else DEFAULT_STATUS


async def current_statuses_for(
    session: AsyncSession, capture_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, ApplicationStatus]:
    """El estado vigente de varias capturas a la vez, para el listado.

    `DISTINCT ON` con el mismo orden que `current_status_event`, mismo
    patrón que `offers_repo.current_extractions_for`: el listado y el
    detalle no pueden discrepar sobre cuál es el estado vigente. Las
    capturas sin ningún evento no aparecen en el resultado; quien llama las
    completa con `DEFAULT_STATUS`.
    """
    if not capture_ids:
        return {}
    rows = (
        (
            await session.execute(
                sa.select(OfferStatusEvent)
                .where(OfferStatusEvent.capture_id.in_(capture_ids))
                .distinct(OfferStatusEvent.capture_id)
                .order_by(
                    OfferStatusEvent.capture_id,
                    OfferStatusEvent.occurred_at.desc(),
                    OfferStatusEvent.id.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.capture_id: row.status for row in rows}


async def status_history(
    session: AsyncSession, capture_id: uuid.UUID
) -> Sequence[OfferStatusEvent]:
    """Toda la línea de tiempo, de la más reciente a la más antigua."""
    return (
        (
            await session.execute(
                sa.select(OfferStatusEvent)
                .where(OfferStatusEvent.capture_id == capture_id)
                .order_by(
                    OfferStatusEvent.occurred_at.desc(), OfferStatusEvent.id.desc()
                )
            )
        )
        .scalars()
        .all()
    )
