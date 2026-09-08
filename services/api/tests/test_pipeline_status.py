"""El repositorio del estado de una candidatura, contra Postgres de verdad.

Igual que `test_repository.py`: la sesión es transaccional, así que todo lo
que estos tests escriben se deshace al terminar.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from futuro_api.models import OfferCapture
from futuro_api.offers import repository as offers_repo
from futuro_api.offers import vocabularies as offers_vocab
from futuro_api.pipeline import repository as repo
from futuro_api.pipeline.vocabularies import ApplicationStatus
from tests.synthetic import ADVERT


async def _capture(session: AsyncSession, text: str = ADVERT) -> OfferCapture:
    return await offers_repo.create_capture(
        session, source=offers_vocab.SourceChannel.PASTE, raw_text=text
    )


async def test_a_fresh_capture_defaults_to_research(session: AsyncSession) -> None:
    """Sin ningún evento, el estado implícito es `research`.

    No se escribe una fila al capturar -es una decisión explícita de esta
    rebanada-, así que el valor por defecto lo pone la lectura, no un
    `INSERT` de más en cada ingesta.
    """
    capture = await _capture(session)
    assert await repo.current_status(session, capture.id) == ApplicationStatus.RESEARCH
    assert await repo.current_status_event(session, capture.id) is None


async def test_recording_a_status_makes_it_current(session: AsyncSession) -> None:
    capture = await _capture(session)
    await repo.record_status(
        session, capture_id=capture.id, status=ApplicationStatus.PREPARING
    )
    assert await repo.current_status(session, capture.id) == ApplicationStatus.PREPARING


async def test_changing_status_adds_a_row_instead_of_replacing_one(
    session: AsyncSession,
) -> None:
    """Cambiar de etapa es una fila nueva: la línea de tiempo no se pierde."""
    capture = await _capture(session)
    await repo.record_status(
        session, capture_id=capture.id, status=ApplicationStatus.RESEARCH
    )
    await repo.record_status(
        session, capture_id=capture.id, status=ApplicationStatus.PREPARING
    )

    history = await repo.status_history(session, capture.id)
    assert [event.status for event in history] == [
        ApplicationStatus.PREPARING,
        ApplicationStatus.RESEARCH,
    ]


async def test_any_transition_is_valid_with_no_order_enforced(
    session: AsyncSession,
) -> None:
    """De `research` directo a `closed`: se descartó sin preparar nada.

    La base de datos no impone una máquina de estados -decisión explícita de
    esta rebanada-, así que saltarse etapas intermedias no es un error.
    """
    capture = await _capture(session)
    await repo.record_status(
        session, capture_id=capture.id, status=ApplicationStatus.RESEARCH
    )
    await repo.record_status(
        session, capture_id=capture.id, status=ApplicationStatus.CLOSED
    )
    assert await repo.current_status(session, capture.id) == ApplicationStatus.CLOSED


async def test_current_statuses_for_only_reports_captures_with_an_event(
    session: AsyncSession,
) -> None:
    with_event = await _capture(session, text=ADVERT)
    without_event = await _capture(session, text=ADVERT + " (otra)")
    await repo.record_status(
        session, capture_id=with_event.id, status=ApplicationStatus.SUBMITTED
    )

    statuses = await repo.current_statuses_for(
        session, [with_event.id, without_event.id]
    )
    assert statuses == {with_event.id: ApplicationStatus.SUBMITTED}


async def test_current_statuses_for_with_no_ids_is_empty(
    session: AsyncSession,
) -> None:
    assert await repo.current_statuses_for(session, []) == {}
