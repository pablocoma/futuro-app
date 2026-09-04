"""Repuntuar el histórico sin volver a llamar al modelo.

Este fichero es la prueba de que la capa `assessment` merece existir. El
contrato la separa de `extraction` porque «repuntuar todo el histórico es
recorrer la base de datos; sin las capas separadas, es volver a pagar la
extracción de cada oferta». Aquí se comprueba justo eso, y con la exigencia
que lo hace convincente: **no aparece ni una llamada al modelo nueva**.

Las ofertas se siembran por el camino real —el trabajo de la cola, con el
cliente simulado— y no construyendo filas a mano. Un test de repuntuación
sobre filas fabricadas probaría la aritmética, que ya tiene sus propios
tests; lo que interesa aquí es que el recorrido funcione sobre lo que la
aplicación guarda de verdad.
"""

from __future__ import annotations

import shutil
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api import data_repo
from futuro_api.assessment import calls, recompute
from futuro_api.assessment import repository as assessment_repo
from futuro_api.assessment import vocabularies as assessment_vocab
from futuro_api.data_repo import loader
from futuro_api.jobs import repository as jobs_repo
from futuro_api.jobs import tasks
from futuro_api.jobs import vocabularies as jobs_vocab
from futuro_api.llm.stub import StubClient
from futuro_api.models import LlmCall, OfferAssessment, VariantRecommendation
from futuro_api.offers import extraction as offer_extraction
from futuro_api.offers import repository as offers_repo
from futuro_api.offers import vocabularies as vocab
from tests.conftest import DATA_REPO, make_settings
from tests.synthetic import ADVERT


def stub() -> StubClient:
    return StubClient(
        {
            offer_extraction.PURPOSE: offer_extraction.canned_draft,
            calls.SCORING_PURPOSE: calls.canned_scoring,
            calls.VARIANT_PURPOSE: calls.canned_variant,
        }
    )


def context(
    sessions: async_sessionmaker[AsyncSession], root: Path | str = DATA_REPO
) -> dict[str, Any]:
    return {
        "sessions": sessions,
        "llm": stub(),
        "settings": make_settings(data_repo_path=str(root)),
        "job_try": 1,
    }


async def seed_scored_offer(
    sessions: async_sessionmaker[AsyncSession],
    *,
    text: str = ADVERT,
    root: Path | str = DATA_REPO,
) -> uuid.UUID:
    """Deja una oferta capturada, extraída y puntuada por el camino real."""
    async with sessions() as session:
        capture = await offers_repo.create_capture(
            session, source=vocab.SourceChannel.PASTE, raw_text=text
        )
        extract_run = await jobs_repo.create_run(
            session,
            kind=jobs_vocab.JobKind.OFFER_EXTRACTION,
            capture_id=capture.id,
        )
        await session.commit()
        capture_id = capture.id
        extract_run_id = extract_run.id

    await tasks.extract_offer(context(sessions, root), str(extract_run_id))

    async with sessions() as session:
        assess_run = await jobs_repo.create_run(
            session,
            kind=jobs_vocab.JobKind.OFFER_ASSESSMENT,
            capture_id=capture_id,
        )
        await session.commit()
        assess_run_id = assess_run.id

    await tasks.assess_offer(context(sessions, root), str(assess_run_id))
    return capture_id


async def current(session: AsyncSession, capture_id: uuid.UUID) -> OfferAssessment:
    saved = await offers_repo.current_extraction(session, capture_id)
    assert saved is not None
    assessment = await assessment_repo.current_assessment(session, saved.id)
    assert assessment is not None
    return assessment


async def count_llm_calls(session: AsyncSession) -> int:
    return (
        await session.execute(sa.select(sa.func.count()).select_from(LlmCall))
    ).scalar_one()


@pytest.fixture
def reweighted_repo(tmp_path: Path) -> Path:
    """Una copia del repositorio de datos con los pesos cambiados.

    Se le da la vuelta al reparto: `ahorro_estimado` baja de 40 a 10 y
    `encaje_de_rol` sube de 10 a 40. La suma sigue siendo 100, así que la
    cobertura no cambia y lo único que puede mover la nota es el reparto.
    Es lo que hace que el test distinga «se ha repuntuado» de «se ha vuelto
    a guardar lo mismo».
    """
    destination = tmp_path / "data_repo"
    shutil.copytree(DATA_REPO, destination)
    path = destination / loader.SCORING_MODEL
    path.write_text(
        path.read_text()
        .replace("ahorro_estimado: 40", "ahorro_estimado: 10")
        .replace("encaje_de_rol: 10", "encaje_de_rol: 40")
    )
    return destination


# ---------------------------------------------------------------------------
# La propiedad que justifica la capa
# ---------------------------------------------------------------------------


async def test_rescoring_the_history_does_not_call_the_model_again(
    sessions: async_sessionmaker[AsyncSession], reweighted_repo: Path
) -> None:
    """El test que el encargo pedía, y su exigencia central.

    Dos ofertas puntuadas, se cambian los pesos, se repuntúa el histórico
    recorriendo la base de datos, y las notas cambian sin que aparezca ni
    una llamada al modelo nueva. Si algún día alguien «optimiza» el
    recálculo llamando al LLM, este test se cae.
    """
    first = await seed_scored_offer(sessions)
    second = await seed_scored_offer(sessions, text=ADVERT + "\nOtra oferta.")

    async with sessions() as session:
        before = {
            capture: (await current(session, capture)).value_score
            for capture in (first, second)
        }
        calls_before = await count_llm_calls(session)

    report = await recompute.recompute_all(sessions, data_repo.load(reweighted_repo))

    assert report.scanned == 2
    assert report.recomputed == 2

    async with sessions() as session:
        assert await count_llm_calls(session) == calls_before
        for capture in (first, second):
            assessment = await current(session, capture)
            assert assessment.source is assessment_vocab.AssessmentSource.RECOMPUTED
            assert assessment.job_run_id is None
            assert assessment.derived_from_id is not None
            assert assessment.value_score != before[capture]
            # Y el peso guardado en la fila es el nuevo, que es lo que hace
            # reproducible la composición de la pantalla.
            weights = {row.dimension: row.weight for row in assessment.dimensions}
            assert weights["ahorro_estimado"] == 10
            assert weights["encaje_de_rol"] == 40


async def test_the_previous_assessment_is_not_touched(
    sessions: async_sessionmaker[AsyncSession], reweighted_repo: Path
) -> None:
    """Append-only: repuntuar inserta, no edita.

    Es lo que hace visible que dos ofertas puntuadas con modelos de scoring
    distintos no son comparables: la fila vieja sigue ahí con su versión y
    su hash.
    """
    capture_id = await seed_scored_offer(sessions)
    async with sessions() as session:
        original = await current(session, capture_id)
        original_id, original_value = original.id, original.value_score
        original_sha = original.scoring_model_sha256

    await recompute.recompute_all(sessions, data_repo.load(reweighted_repo))

    async with sessions() as session:
        old = await session.get(OfferAssessment, original_id)
        assert old is not None
        assert old.value_score == original_value
        assert old.source is assessment_vocab.AssessmentSource.LLM
        new = await current(session, capture_id)
        assert new.id != original_id
        assert new.scoring_model_sha256 != original_sha


async def test_rescoring_leaves_the_chosen_variant_alone(
    sessions: async_sessionmaker[AsyncSession], reweighted_repo: Path
) -> None:
    """La razón por la que la variante es una tabla aparte.

    No se puede recalcular sin llamar al modelo, así que repuntuar no la
    toca. Si viviera como columnas del assessment, cada repuntuación tendría
    que pagar otra llamada o arrastrar la elección anterior.
    """
    await seed_scored_offer(sessions)
    async with sessions() as session:
        recommendations_before = (
            await session.execute(
                sa.select(sa.func.count()).select_from(VariantRecommendation)
            )
        ).scalar_one()

    await recompute.recompute_all(sessions, data_repo.load(reweighted_repo))

    async with sessions() as session:
        assert (
            await session.execute(
                sa.select(sa.func.count()).select_from(VariantRecommendation)
            )
        ).scalar_one() == recommendations_before


async def test_rescoring_is_idempotent(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Lanzarlo dos veces con el mismo modelo no duplica filas.

    Se decide por el `sha256` del YAML y no por su `version`, que es lo que
    permite lanzarlo sin pensar después de tocar el fichero.
    """
    await seed_scored_offer(sessions)
    repo = data_repo.load(DATA_REPO)

    report = await recompute.recompute_all(sessions, repo)
    assert report.recomputed == 0
    assert report.already_current == 1

    forced = await recompute.recompute_all(sessions, repo, force=True)
    assert forced.recomputed == 1


async def test_an_offer_without_a_previous_assessment_is_reported_not_invented(
    sessions: async_sessionmaker[AsyncSession], reweighted_repo: Path
) -> None:
    """Sin juicios previos no hay nada que recalcular.

    Este módulo no llama al modelo, así que una oferta extraída y sin
    puntuar se queda como está y se cuenta aparte. Inventarle notas sería
    justo lo contrario de lo que hace.
    """
    async with sessions() as session:
        capture = await offers_repo.create_capture(
            session, source=vocab.SourceChannel.PASTE, raw_text=ADVERT
        )
        run = await jobs_repo.create_run(
            session,
            kind=jobs_vocab.JobKind.OFFER_EXTRACTION,
            capture_id=capture.id,
        )
        await session.commit()
        run_id = run.id
    await tasks.extract_offer(context(sessions), str(run_id))

    report = await recompute.recompute_all(sessions, data_repo.load(reweighted_repo))
    assert report.scanned == 1
    assert report.recomputed == 0
    assert report.without_assessment == 1


# ---------------------------------------------------------------------------
# Los casos que el modelo de scoring puede traer
# ---------------------------------------------------------------------------


async def test_a_dimension_new_in_the_scoring_model_stays_unscored(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """No se le puede inventar nota, así que baja la cobertura.

    Y si la cobertura cae por debajo del mínimo, la oferta se queda sin
    puntuación hasta que alguien la vuelva a puntuar de verdad. Es lo
    honesto: nadie ha mirado esa dimensión. Aquí se añade una dimensión de
    peso 100, que deja la cobertura en 100/200 = 0,500, por debajo del 0,60
    que exige el modelo sintético.
    """
    capture_id = await seed_scored_offer(sessions)
    destination = tmp_path / "data_repo"
    shutil.copytree(DATA_REPO, destination)
    path = destination / loader.SCORING_MODEL
    path.write_text(
        path.read_text()
        .replace("weights:", "weights:\n  prestigio_del_puerto: 100", 1)
        .replace(
            "anchors:",
            "anchors:\n  prestigio_del_puerto:\n    0: Nadie lo conoce.\n"
            "    5: Abre puertas por sí solo.",
            1,
        )
    )

    await recompute.recompute_all(sessions, data_repo.load(destination))

    async with sessions() as session:
        assessment = await current(session, capture_id)
        new = next(
            row
            for row in assessment.dimensions
            if row.dimension == "prestigio_del_puerto"
        )
        assert new.score is None
        assert "nunca se puntuó" in (new.unscored_reason or "")
        assert assessment.value_score is None
        assert assessment.coverage < Decimal("0.60")
        assert any(
            correction["rule"] == "dimension_new_in_scoring_model"
            for correction in assessment.corrections
        )


async def test_a_dimension_gone_from_the_scoring_model_is_dropped(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    capture_id = await seed_scored_offer(sessions)
    destination = tmp_path / "data_repo"
    shutil.copytree(DATA_REPO, destination)
    path = destination / loader.SCORING_MODEL
    path.write_text(path.read_text().replace("  ubicacion: 20\n", ""))

    await recompute.recompute_all(sessions, data_repo.load(destination))

    async with sessions() as session:
        assessment = await current(session, capture_id)
        assert "ubicacion" not in {row.dimension for row in assessment.dimensions}
        assert any(
            correction["rule"] == "dimension_gone_from_scoring_model"
            for correction in assessment.corrections
        )


async def test_an_evidence_that_stopped_holding_degrades_the_match(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    """Lo único que se revisa y no es aritmética.

    Un `meets` apoyado en un bullet que desde entonces ha dejado de ser
    divulgable ya no se sostiene, y eso se puede saber sin preguntarle a
    nadie. Es la consecuencia útil de que el cruce viva en esta capa y no en
    la extracción: si viviera allí, volver a cruzar exigiría reextraer.
    """
    capture_id = await seed_scored_offer(sessions)
    async with sessions() as session:
        before = await current(session, capture_id)
        meets = [
            row.evidence_ref
            for row in before.requirement_matches
            if row.evidence_ref is not None
        ]
        assert meets, "el stub tiene que dejar algún cruce con evidencia"

    destination = tmp_path / "data_repo"
    shutil.copytree(DATA_REPO, destination)
    path = destination / loader.BULLET_BANK
    path.write_text(
        path.read_text().replace(
            "cv_usage: eligible_with_internal_policy_check", "cv_usage: blocked"
        )
    )

    await recompute.recompute_all(sessions, data_repo.load(destination), force=True)

    async with sessions() as session:
        after = await current(session, capture_id)
        assert all(row.evidence_ref is None for row in after.requirement_matches)
        assert all(row.match.value != "meets" for row in after.requirement_matches)
        assert any(
            correction["rule"] == "evidence_ref_no_longer_holds"
            for correction in after.corrections
        )


async def test_the_corrections_of_the_previous_row_are_not_carried_forward(
    sessions: async_sessionmaker[AsyncSession], reweighted_repo: Path
) -> None:
    """Eran la cuenta de infracciones del modelo, y esta fila no le preguntó.

    Arrastrarlas contaría dos veces la misma infracción cada vez que se
    repuntúa, y esa cuenta es la que decide si hay que cambiar el prompt.
    """
    capture_id = await seed_scored_offer(sessions)
    await recompute.recompute_all(sessions, data_repo.load(reweighted_repo))

    async with sessions() as session:
        assessment = await current(session, capture_id)
        rules_applied = {correction["rule"] for correction in assessment.corrections}
        # Solo reglas de recálculo, ninguna de validación de respuesta.
        assert not rules_applied & {
            "score_without_citation",
            "verdict_without_citation",
            "unknown_dimension",
        }
