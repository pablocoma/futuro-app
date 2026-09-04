"""Las dos llamadas al modelo de M2, y sus respuestas simuladas.

Es la costura entre `assessment/` y `llm/`. El módulo de LLM sigue sin saber
qué es una oferta: recibe un prompt y un esquema, y este fichero es el único
que sabe cuáles son los de puntuar y de elegir variante.

Dos propósitos distintos y no uno, aunque los ejecute el mismo trabajo:
`llm_calls.purpose` es lo que permite mirar cuánto cuesta puntuar y cuánto
cuesta elegir variante por separado, en vez de un total ciego. Es también la
razón por la que `job_runs` y `llm_calls` son dos tablas desde M1: aquí
aparece por fin el trabajo que hace más de una llamada.
"""

from __future__ import annotations

from futuro_api.assessment import prompt, schemas
from futuro_api.assessment import vocabularies as vocab
from futuro_api.assessment.brief import OfferBrief
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.data_repo.models import DataRepo
from futuro_api.llm import LlmClient, LlmResult
from futuro_api.offers import vocabularies as offers_vocab
from futuro_api.offers.extraction import advert_from_prompt
from futuro_api.offers.rules import MIN_QUOTE_CHARS

SCORING_PURPOSE = "offer_scoring"
VARIANT_PURPOSE = "cv_variant_choice"

# Cuántas dimensiones puntúa la respuesta simulada: la mitad, redondeando
# hacia arriba. Con los dos modelos de scoring que existen —el real de seis
# dimensiones y el sintético de cuatro— eso deja la cobertura por encima del
# mínimo, así que el camino que sí emite puntuación se recorre en local; y
# deja dimensiones sin puntuar, así que el hueco rayado de la pantalla
# también se ve sin tener que provocarlo.
_STUB_SCORED_FRACTION = 2


async def score(
    client: LlmClient, repo: DataRepo, brief: OfferBrief, raw_text: str
) -> LlmResult[schemas.ScoringDraft]:
    """Pide la puntuación de una oferta ya extraída.

    Devuelve la respuesta **sin validar**: lo que sale de aquí puede tener
    notas sin cita, citas inventadas y filtros dados por superados sin
    comprobar. Pasarlo por `rules.validate_scoring` antes de guardarlo no es
    opcional.
    """
    return await client.structured(
        purpose=SCORING_PURPOSE,
        system=prompt.SCORING_SYSTEM_PROMPT,
        user=prompt.build_scoring_prompt(repo, brief, raw_text),
        schema=schemas.ScoringDraft,
    )


async def choose_variant(
    client: LlmClient, repo: DataRepo, brief: OfferBrief, raw_text: str
) -> LlmResult[schemas.VariantChoiceDraft]:
    """Pide la variante de CV que mejor encaja con la oferta."""
    return await client.structured(
        purpose=VARIANT_PURPOSE,
        system=prompt.VARIANT_SYSTEM_PROMPT,
        user=prompt.build_variant_prompt(repo, brief, raw_text),
        schema=schemas.VariantChoiceDraft,
    )


def _quotable_lines(user_prompt: str) -> list[str]:
    """Líneas del anuncio que sirven de cita.

    Del anuncio y no escritas a mano, que es lo que convierte al cliente
    simulado de comodidad en herramienta: la verificación de citas de
    `rules.py` se ejecuta de verdad y pasa con cualquier anuncio pegado, así
    que en local se recorre el camino real. Con citas fijas, cualquier texto
    distinto del de los tests dejaría todas las dimensiones sin puntuar y
    nunca se vería una barra.
    """
    advert = advert_from_prompt(user_prompt)
    return [
        line
        for line in (raw.strip() for raw in advert.splitlines())
        if len(line) >= MIN_QUOTE_CHARS
    ]


def canned_scoring(user_prompt: str) -> schemas.ScoringDraft:
    """Una puntuación simulada, coherente con lo que se le ha preguntado.

    Las dimensiones, los filtros, las evidencias y los requisitos salen del
    propio prompt y no del repositorio de datos. Ver el comentario de
    `prompt.dimensions_in`: el cliente se construye al arrancar el worker y
    el cargador relee los YAML en cada trabajo, así que contestar sobre una
    copia propia sería contestar sobre otro modelo de scoring en cuanto
    alguien editase un peso.

    Puntúa poco a propósito y dice en cada motivo que es simulada, que es lo
    que se ve en la pantalla: una puntuación simulada no se puede confundir
    con una real ni leyendo el detalle.
    """
    lines = _quotable_lines(user_prompt)
    dimensions = prompt.dimensions_in(user_prompt)
    gates = prompt.gates_in(user_prompt)
    evidence = prompt.usable_evidence_in(user_prompt)
    positions = prompt.requirement_positions_in(user_prompt)

    def quote(index: int) -> str | None:
        return lines[index % len(lines)] if lines else None

    scored_until = (len(dimensions) + _STUB_SCORED_FRACTION - 1) // (
        _STUB_SCORED_FRACTION
    )
    scores = []
    for index, name in enumerate(dimensions):
        citation = quote(index) if index < scored_until else None
        scores.append(
            schemas.DimensionScore(
                dimension=name,
                # Una nota media y no un 5: un stub que puntuara alto haría
                # que toda oferta pegada en local pareciera excelente.
                score=3 if citation else None,
                citation=citation,
                reason=(
                    "puntuación simulada: no se ha llamado a ningún modelo"
                    if citation
                    else "puntuación simulada: esta dimensión se deja sin puntuar "
                    "para que se vea el hueco de lo no puntuable"
                ),
            )
        )

    verdicts = []
    for index, name in enumerate(gates):
        # El primero se decide con una cita del anuncio y el resto quedan
        # pendientes: así el camino del veredicto con cita y el del filtro
        # sin datos se recorren los dos en cada trabajo simulado.
        decisive = index == 0 and bool(lines)
        verdicts.append(
            schemas.GateVerdict(
                gate=name,
                status=(
                    vocab.GateStatus.PASS if decisive else vocab.GateStatus.PENDING
                ),
                citation=quote(0) if decisive else None,
                reason=(
                    "evaluación simulada"
                    if decisive
                    else "evaluación simulada: el filtro queda pendiente"
                ),
            )
        )

    crosses = []
    for index, position in enumerate(positions):
        # Con evidencia utilizable se afirma `meets`, que es el camino que
        # obliga a que la referencia resuelva de verdad contra el banco; sin
        # ella, `no_evidence`, que es lo honesto.
        reference = evidence[index % len(evidence)] if evidence else None
        crosses.append(
            schemas.RequirementCross(
                requirement_index=position,
                match=(
                    offers_vocab.RequirementMatch.MEETS
                    if reference
                    else offers_vocab.RequirementMatch.NO_EVIDENCE
                ),
                evidence_ref=reference,
                reason="cruce simulado contra el banco de evidencias",
            )
        )

    return schemas.ScoringDraft(
        dimensions=scores,
        gates=verdicts,
        requirements=crosses,
        probability_band=data_vocab.ProbabilityBand.MEDIUM,
        probability_reason=(
            "banda simulada: no se ha comparado el perfil con nada, así que "
            "esta banda no significa nada"
        ),
    )


def canned_variant(user_prompt: str) -> schemas.VariantChoiceDraft:
    """Una elección de variante simulada.

    Elige la primera de las que el prompt declara disponibles. Si no hubiera
    ninguna, devuelve una cadena vacía a propósito y no una inventada: así
    lo caza `rules.validate_variant` y el trabajo falla con el motivo, en vez
    de guardar una recomendación que apunta a un documento que no existe.
    """
    available = prompt.variants_in(user_prompt)
    return schemas.VariantChoiceDraft(
        variant=available[0] if available else "",
        confidence=offers_vocab.Confidence.LOW,
        reason=(
            "elección simulada: no se ha llamado a ningún modelo, así que la "
            "variante es simplemente la primera de la lista"
        ),
    )
