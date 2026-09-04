"""Repuntuar el histórico sin volver a llamar al modelo.

Este módulo es la prueba de que la capa `assessment` merece existir. El
contrato dice que se separa de `extraction` porque «`assessment` se recalcula
sin volver a llamar al LLM: con las capas separadas, repuntuar todo el
histórico es recorrer la base de datos; sin ellas, es volver a pagar la
extracción de cada oferta». Aquí está ese recorrido, y
`tests/test_recompute.py` comprueba justo eso: que después de cambiar los
pesos, las notas cambian y **no hay ni una llamada al modelo nueva**.

Lo que se conserva de la fila anterior es lo que juzgó el modelo: la nota de
cada dimensión, su cita, su motivo, el estado de cada filtro y la banda de
probabilidad. Lo que se recalcula es todo lo que calcula el código, con el
modelo de scoring de hoy: pesos, anclas, media ponderada, renormalización,
cobertura, cubo y esfuerzo.

Hay una cosa más que se vuelve a comprobar, y no es aritmética: **las
referencias a evidencias**. Un `meets` apoyado en un bullet que desde
entonces ha pasado a `blocked` deja de sostenerse, y eso se puede saber sin
preguntarle a nadie. Repuntuar lo degrada a `partial` y lo registra. Es la
consecuencia útil de que el cruce viva en esta capa y no en la extracción.

Se ejecuta a mano dentro del contenedor y no tiene pantalla ni endpoint:

    docker compose exec worker python -m futuro_api.assessment.recompute

No es un trabajo de la cola a propósito. Un tercer tipo de `job_runs` para
esto exigiría justificar qué significa reintentarlo y qué pasa si se queda a
medias, cuando lo que hace es idempotente y se puede volver a lanzar sin
consecuencias: una fila ya repuntuada con el modelo de hoy se salta.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from futuro_api import data_repo, db
from futuro_api.assessment import repository as assessment_repo
from futuro_api.assessment import scoring
from futuro_api.assessment import vocabularies as vocab
from futuro_api.assessment.rules import ValidatedRequirementMatch, ValidatedScoring
from futuro_api.assessment.scoring import ResolvedGate, ScoredDimension
from futuro_api.config import Settings, get_settings
from futuro_api.data_repo.models import DataRepo
from futuro_api.models import OfferAssessment, OfferExtraction
from futuro_api.offers import vocabularies as offers_vocab
from futuro_api.offers.rules import Correction, enforce_match_rule

logger = logging.getLogger(__name__)

# Cuántas ofertas se leen por vuelta. La paginación va por identificador de
# captura y no por desplazamiento: el barrido puede tardar y una captura
# nueva en medio descuadraría un `OFFSET`.
PAGE = 50


class Skipped(StrEnum):
    """Por qué una oferta no se repuntúa. Explícito y no un `None` a secas.

    Lo que se quería evitar: que quien recorre tenga que volver a consultar
    la base de datos para averiguar por qué la función anterior no devolvió
    nada. Dos consultas para reconstruir algo que la primera ya sabía.
    """

    NO_ASSESSMENT = "sin puntuación previa"
    ALREADY_CURRENT = "ya se puntuó con este modelo de scoring"


@dataclass
class Report:
    """Qué hizo el barrido. Se imprime al terminar."""

    scanned: int = 0
    recomputed: int = 0
    without_assessment: int = 0
    already_current: int = 0

    def render(self) -> str:
        return (
            f"{self.scanned} ofertas recorridas: {self.recomputed} repuntuadas, "
            f"{self.already_current} ya estaban al día, "
            f"{self.without_assessment} sin puntuación previa"
        )


def _dimensions_for(
    repo: DataRepo, previous: OfferAssessment, corrections: list[Correction]
) -> tuple[ScoredDimension, ...]:
    """Las dimensiones del modelo de hoy, con las notas de la fila anterior.

    Tres casos, y el segundo es el que hay que leer despacio:

    - una dimensión que sigue estando y ya tenía nota: se conserva la nota,
      la cita y el motivo, y se le aplican el **peso y el ancla de hoy**. Es
      lo que hace que repuntuar signifique algo.
    - una dimensión **nueva** en el modelo de scoring: no se le puede
      inventar nota, así que queda sin puntuar con ese motivo. Consecuencia
      que hay que aceptar: la cobertura baja, y si cae por debajo del mínimo
      la oferta se queda sin puntuación hasta que alguien la vuelva a
      puntuar de verdad. Es lo honesto: nadie ha mirado esa dimensión.
    - una dimensión que **ya no está** en el modelo: se descarta con su
      corrección. La fila vieja la conserva, que es para lo que sirve no
      borrar nada.
    """
    stored = {row.dimension: row for row in previous.dimensions}
    resolved = []
    for dimension in repo.scoring.dimensions:
        row = stored.get(dimension.name)
        if row is None:
            corrections.append(
                Correction(
                    field=f"dimensions.{dimension.name}",
                    rule="dimension_new_in_scoring_model",
                    detail=(
                        "el modelo de scoring ha ganado esta dimensión después "
                        "de puntuar esta oferta; queda sin puntuar porque nadie "
                        "la ha mirado"
                    ),
                )
            )
            resolved.append(
                ScoredDimension(
                    name=dimension.name,
                    weight=dimension.weight,
                    score=None,
                    citation=None,
                    reason=None,
                    anchor=None,
                    unscored_reason=(
                        "dimensión nueva en el modelo de scoring; nunca se puntuó"
                    ),
                )
            )
            continue
        resolved.append(
            ScoredDimension(
                name=dimension.name,
                weight=dimension.weight,
                score=row.score,
                citation=row.citation,
                reason=row.reason,
                anchor=(
                    dimension.anchor_for(row.score) if row.score is not None else None
                ),
                unscored_reason=row.unscored_reason,
            )
        )

    for name in stored:
        if repo.scoring.dimension(name) is None:
            corrections.append(
                Correction(
                    field=f"dimensions.{name}",
                    rule="dimension_gone_from_scoring_model",
                    detail=(
                        "el modelo de scoring ya no tiene esta dimensión; su "
                        "nota se queda en la puntuación anterior y no cuenta "
                        "en esta"
                    ),
                    previous=name,
                )
            )
    return tuple(resolved)


def _gates_for(
    repo: DataRepo, previous: OfferAssessment, corrections: list[Correction]
) -> tuple[ResolvedGate, ...]:
    """Los filtros de hoy, con los veredictos de la fila anterior.

    Un filtro nuevo queda `pending`, que es la regla del propio modelo de
    scoring: un filtro que no se ha podido evaluar nunca se supone superado.
    """
    stored = {row.gate: row for row in previous.gates}
    resolved = []
    for gate in repo.scoring.gates:
        row = stored.get(gate.name)
        if row is None:
            corrections.append(
                Correction(
                    field=f"gates.{gate.name}",
                    rule="gate_new_in_scoring_model",
                    detail=(
                        "el modelo de scoring ha ganado este filtro después de "
                        "puntuar esta oferta; queda pendiente"
                    ),
                )
            )
            resolved.append(
                ResolvedGate(
                    name=gate.name,
                    status=vocab.GateStatus.PENDING,
                    citation=None,
                    reason="filtro nuevo en el modelo de scoring; nunca se evaluó",
                )
            )
            continue
        resolved.append(
            ResolvedGate(
                name=gate.name,
                status=row.status,
                citation=row.citation,
                reason=row.reason,
            )
        )
    return tuple(resolved)


def _matches_for(
    repo: DataRepo,
    previous: OfferAssessment,
    positions: dict[uuid.UUID, int],
    corrections: list[Correction],
) -> tuple[ValidatedRequirementMatch, ...]:
    """Los cruces de la fila anterior, revisados contra el banco de hoy.

    Lo único de aquí que no es copiar: si la evidencia en la que se apoyaba
    un `meets` ha dejado de estar `verified` o de ser divulgable, la
    referencia se cae y el `meets` se degrada a `partial`. Se puede
    comprobar sin llamar a nadie, así que forma parte de lo que significa
    recalcular.
    """
    matches = []
    for row in previous.requirement_matches:
        position = positions.get(row.requirement_id)
        if position is None:  # pragma: no cover - la FK en cascada lo impide
            continue
        reference = row.evidence_ref
        if reference is not None:
            bullet = repo.bullet(reference)
            if bullet is None or not bullet.usable:
                corrections.append(
                    Correction(
                        field=f"requirements[{position}].evidence_ref",
                        rule="evidence_ref_no_longer_holds",
                        detail=(
                            "la evidencia en la que se apoyaba este cruce ya no "
                            "existe, o ya no está comprobada y divulgable"
                        ),
                        previous=reference,
                    )
                )
                reference = None
        match, correction = enforce_match_rule(
            f"requirements[{position}].match", row.match, reference
        )
        if correction is not None:
            corrections.append(correction)
        matches.append(
            ValidatedRequirementMatch(
                requirement_position=position,
                match=match or offers_vocab.RequirementMatch.NO_EVIDENCE,
                evidence_ref=reference,
                reason=row.reason,
            )
        )
    return tuple(matches)


async def recompute_one(
    session: AsyncSession,
    repo: DataRepo,
    extraction: OfferExtraction,
    *,
    force: bool = False,
) -> OfferAssessment | Skipped:
    """Repuntúa una oferta, o dice por qué no.

    No hay nada que repuntuar si la oferta no tenía puntuación previa —no
    hay juicios del modelo que reutilizar, y este módulo no llama a
    ninguno— o si la que tiene ya se hizo con el modelo de scoring de hoy.
    Lo segundo se decide por el `sha256` y no por la versión declarada, y es
    lo que hace el barrido idempotente: lanzarlo dos veces no duplica filas.
    """
    previous = await assessment_repo.current_assessment(session, extraction.id)
    if previous is None:
        return Skipped.NO_ASSESSMENT
    if not force and previous.scoring_model_sha256 == repo.scoring.sha256:
        return Skipped.ALREADY_CURRENT

    corrections: list[Correction] = []
    dimensions = _dimensions_for(repo, previous, corrections)
    gates = _gates_for(repo, previous, corrections)
    requirement_ids = {r.position: r.id for r in extraction.requirements}
    positions = {r.id: r.position for r in extraction.requirements}
    matches = _matches_for(repo, previous, positions, corrections)

    computed = scoring.compute(
        repo.scoring,
        dimensions=dimensions,
        gates=gates,
        band=previous.probability_band,
        role_family=(extraction.role_family.value if extraction.role_family else None),
        core_role_families=repo.core_role_families,
    )
    # Las correcciones de la fila anterior **no** se arrastran: eran la
    # cuenta de cuántas veces el modelo se saltó las reglas al responder, y
    # esta fila no le ha preguntado nada. Arrastrarlas contaría dos veces la
    # misma infracción cada vez que se repuntúa.
    validated = ValidatedScoring(
        dimensions=dimensions,
        gates=gates,
        probability_band=previous.probability_band,
        probability_reason=previous.probability_reason,
        requirement_matches=matches,
        corrections=tuple(corrections),
    )
    return await assessment_repo.save_assessment(
        session,
        extraction_id=extraction.id,
        job_run_id=None,
        source=vocab.AssessmentSource.RECOMPUTED,
        derived_from_id=previous.id,
        scoring_model_version=repo.scoring.version,
        scoring_model_sha256=repo.scoring.sha256,
        prompt_version=None,
        model=None,
        validated=validated,
        computed=computed,
        requirement_ids=requirement_ids,
    )


async def recompute_all(
    sessions: async_sessionmaker[AsyncSession],
    repo: DataRepo,
    *,
    force: bool = False,
) -> Report:
    """Recorre la base de datos entera repuntuando lo que haga falta.

    Una transacción por página y no una para todo: un barrido de mil ofertas
    en una sola transacción bloquearía filas durante minutos, y si fallara a
    mitad no habría avanzado nada. Por páginas, lo hecho queda hecho y
    volver a lanzarlo continúa.
    """
    report = Report()
    after: uuid.UUID | None = None
    while True:
        async with sessions() as session:
            page = await assessment_repo.scorable_extractions(
                session, limit=PAGE, after=after
            )
            if not page:
                break
            for extraction in page:
                report.scanned += 1
                outcome = await recompute_one(session, repo, extraction, force=force)
                if outcome is Skipped.NO_ASSESSMENT:
                    report.without_assessment += 1
                elif outcome is Skipped.ALREADY_CURRENT:
                    report.already_current += 1
                else:
                    report.recomputed += 1
            after = page[-1].capture_id
            await session.commit()
    return report


async def main(settings: Settings | None = None, *, force: bool = False) -> Report:
    settings = settings or get_settings()
    root = settings.data_repo_root
    if root is None:
        raise SystemExit(
            "no hay repositorio de datos configurado (DATA_REPO_PATH): sin "
            "modelo de scoring no hay nada con lo que repuntuar"
        )
    repo = data_repo.load(root)
    engine = db.create_engine(settings.database_url)
    try:
        report = await recompute_all(
            db.create_session_factory(engine), repo, force=force
        )
    finally:
        await engine.dispose()
    return report


def run() -> None:  # pragma: no cover - punto de entrada de la línea de órdenes
    parser = argparse.ArgumentParser(
        description=(
            "Repuntúa las ofertas ya extraídas con el modelo de scoring "
            "actual, sin llamar al LLM."
        )
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "repuntúa también las que ya se puntuaron con este mismo modelo "
            "de scoring; por omisión se saltan"
        ),
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    report = asyncio.run(main(force=arguments.force))
    print(report.render())


if __name__ == "__main__":  # pragma: no cover
    run()
