"""Donde el código valida lo que el modelo juzgó.

En M1 el principio era «el LLM elige y cita, el código valida». Aquí es
distinto y más exigente: **el LLM juzga y el código calcula**. El modelo
pone la nota, la cita que la sostiene y el motivo; todo lo demás —la media
ponderada, la renormalización, la cobertura, el cubo y el esfuerzo— sale de
`scoring.py`, que no ve al modelo.

Las tres clases de respuesta a un incumplimiento son las mismas que en la
extracción, y la del medio es la que manda el contrato:

1. **Rechazo** (`AssessmentRejected`, no se guarda nada) cuando no hay
   degradación honesta: una banda de probabilidad sin motivo, un juego de
   dimensiones que no es del modelo de scoring, la misma dimensión puntuada
   dos veces con notas distintas, o una variante que no existe.
2. **Sin puntuar** cuando la nota no se sostiene. «Una nota sin cita es
   inválida y esa dimensión queda sin puntuar»: no se corrige la nota, se
   quita. Vale para la cita que falta, la que no aparece en el anuncio y la
   nota fuera de escala.
3. **Degradación al máximo que el contrato permite**: un filtro que decide
   sin cita comprobable pasa a `pending` —nunca a `fail`, porque «no
   consta» no es «incumple»— y un `meets` sin evidencia que resuelva pasa a
   `partial`.

La verificación de citas es **la misma función** que usa la extracción,
`offers.rules.normalise`. No es reutilización por ahorrar código: es que
«una cita se comprueba contra el anuncio» tiene que significar exactamente
lo mismo en las dos capas, y con dos implementaciones acabaría no
significándolo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from futuro_api.assessment import schemas
from futuro_api.assessment import vocabularies as vocab
from futuro_api.assessment.scoring import ResolvedGate, ScoredDimension
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.data_repo.models import DataRepo, ScoringModel, VariantGuide
from futuro_api.offers import vocabularies as offers_vocab
from futuro_api.offers.rules import (
    MIN_QUOTE_CHARS,
    Correction,
    enforce_match_rule,
    normalise,
)

# Lo que se guarda cuando el modelo deja un motivo vacío. La columna es NOT
# NULL y un motivo en blanco en pantalla parece un fallo de la aplicación;
# así se ve que el hueco lo dejó el modelo, y queda contado en
# `corrections`.
NO_REASON = "el modelo no dio motivo"


class AssessmentRejected(Exception):
    """El modelo devolvió algo que no se puede guardar sin inventar."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


@dataclass(frozen=True)
class ValidatedRequirementMatch:
    """El cruce de un requisito, ya comprobado contra el banco de bullets."""

    requirement_position: int
    match: offers_vocab.RequirementMatch
    evidence_ref: str | None
    reason: str


@dataclass(frozen=True)
class ValidatedScoring:
    """Lo que se puede guardar de una respuesta de scoring."""

    dimensions: tuple[ScoredDimension, ...]
    gates: tuple[ResolvedGate, ...]
    probability_band: data_vocab.ProbabilityBand
    probability_reason: str
    requirement_matches: tuple[ValidatedRequirementMatch, ...]
    corrections: tuple[Correction, ...]


@dataclass(frozen=True)
class ValidatedVariant:
    """La variante elegida, ya comprobada contra las que existen."""

    variant: str
    confidence: offers_vocab.Confidence
    reason: str


@dataclass
class _Accumulator:
    haystack: str
    violations: list[str] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)


def _clean(text: str | None) -> str:
    return (text or "").strip()


def _quote_holds(quote: str | None, acc: _Accumulator) -> bool:
    """Si una cita es utilizable: existe, no es un fragmento inútil y aparece.

    El mínimo de tres caracteres y la normalización son los de M1, con el
    mismo criterio: se perdona lo que un modelo cambia al copiar —espacios,
    comillas curvas, mayúsculas— y no se perdona nada más.
    """
    quote = _clean(quote)
    if len(quote) < MIN_QUOTE_CHARS:
        return False
    return normalise(quote) in acc.haystack


def _dimensions(
    draft: schemas.ScoringDraft, model: ScoringModel, acc: _Accumulator
) -> tuple[ScoredDimension, ...]:
    """Una fila por dimensión del modelo de scoring, en su orden.

    Siempre las del YAML y solo las del YAML: lo que el modelo se invente se
    descarta, y lo que se deje sin contestar queda sin puntuar con su
    motivo. Así la pantalla puede pintar el hueco rayado de una dimensión
    que nadie miró, que es justo lo que se quiere ver.
    """
    known = set(model.dimension_names)
    answered: dict[str, schemas.DimensionScore] = {}
    for entry in draft.dimensions:
        name = _clean(entry.dimension)
        if name not in known:
            acc.corrections.append(
                Correction(
                    field=f"dimensions.{name or '(sin nombre)'}",
                    rule="unknown_dimension",
                    detail=(
                        "el modelo puntuó una dimensión que el modelo de "
                        "scoring no tiene; se descarta"
                    ),
                    previous=name or None,
                )
            )
            continue
        if name in answered:
            previous = answered[name]
            if previous.score != entry.score:
                # Dos notas distintas para la misma dimensión: elegir una
                # sería adivinar cuál quiso decir.
                acc.violations.append(
                    f"la dimensión «{name}» viene puntuada dos veces con notas "
                    f"distintas ({previous.score} y {entry.score})"
                )
                continue
            acc.corrections.append(
                Correction(
                    field=f"dimensions.{name}",
                    rule="duplicated_dimension",
                    detail="venía repetida con la misma nota; se guarda una vez",
                )
            )
            continue
        answered[name] = entry

    if draft.dimensions and not answered:
        acc.violations.append(
            "ninguna de las dimensiones que devolvió el modelo es del modelo de "
            f"scoring; se esperaban {sorted(known)}"
        )

    resolved = []
    for dimension in model.dimensions:
        scored = answered.get(dimension.name)
        if scored is None:
            acc.corrections.append(
                Correction(
                    field=f"dimensions.{dimension.name}",
                    rule="missing_dimension",
                    detail="el modelo no la devolvió; queda sin puntuar",
                )
            )
            resolved.append(
                _unscored(dimension.name, dimension.weight, "el modelo no la evaluó")
            )
            continue

        reason = _clean(scored.reason) or NO_REASON
        if scored.score is None:
            # El modelo dice que no la puede puntuar. Es una respuesta
            # legítima y frecuente —en Europa casi ninguna oferta publica
            # salario— así que no es una corrección: es el camino previsto.
            resolved.append(_unscored(dimension.name, dimension.weight, reason))
            continue

        if not model.score_min <= scored.score <= model.score_max:
            acc.corrections.append(
                Correction(
                    field=f"dimensions.{dimension.name}",
                    rule="score_out_of_scale",
                    detail=(
                        f"la nota está fuera de la escala "
                        f"[{model.score_min}, {model.score_max}]; la dimensión "
                        "queda sin puntuar en vez de recortarla, que sería "
                        "inventarse una nota"
                    ),
                    previous=str(scored.score),
                )
            )
            resolved.append(
                _unscored(
                    dimension.name, dimension.weight, "la nota venía fuera de escala"
                )
            )
            continue

        if not _quote_holds(scored.citation, acc):
            quote = _clean(scored.citation)
            acc.corrections.append(
                Correction(
                    field=f"dimensions.{dimension.name}",
                    rule="score_without_citation",
                    detail=(
                        "una nota sin cita que aparezca en el anuncio no es "
                        "válida; la dimensión queda sin puntuar"
                    ),
                    previous=str(scored.score),
                    applied=quote[:120] or None,
                )
            )
            resolved.append(
                _unscored(
                    dimension.name,
                    dimension.weight,
                    "la nota no venía sostenida por una cita del anuncio",
                )
            )
            continue

        resolved.append(
            ScoredDimension(
                name=dimension.name,
                weight=dimension.weight,
                score=scored.score,
                citation=_clean(scored.citation),
                reason=reason,
                anchor=dimension.anchor_for(scored.score),
                unscored_reason=None,
            )
        )
    return tuple(resolved)


def _unscored(name: str, weight: int, why: str) -> ScoredDimension:
    return ScoredDimension(
        name=name,
        weight=weight,
        score=None,
        citation=None,
        reason=None,
        anchor=None,
        unscored_reason=why,
    )


def _gates(
    draft: schemas.ScoringDraft, model: ScoringModel, acc: _Accumulator
) -> tuple[ResolvedGate, ...]:
    """Un veredicto por filtro del modelo de scoring, en su orden.

    Un filtro que el modelo no contesta, o que decide sin una cita que
    aparezca en el anuncio, queda en `pending`. Nunca en `fail`: la regla
    del YAML es «un filtro que no puede evaluarse queda pending, nunca se
    supone superado», y su simétrica también vale —tampoco se supone
    incumplido—.
    """
    known = set(model.gate_names)
    answered: dict[str, schemas.GateVerdict] = {}
    for verdict in draft.gates:
        name = _clean(verdict.gate)
        if name not in known:
            acc.corrections.append(
                Correction(
                    field=f"gates.{name or '(sin nombre)'}",
                    rule="unknown_gate",
                    detail=(
                        "el modelo evaluó un filtro que el modelo de scoring no "
                        "tiene; se descarta"
                    ),
                    previous=name or None,
                )
            )
            continue
        answered.setdefault(name, verdict)

    resolved = []
    for gate in model.gates:
        answer = answered.get(gate.name)
        if answer is None:
            acc.corrections.append(
                Correction(
                    field=f"gates.{gate.name}",
                    rule="missing_gate",
                    detail="el modelo no lo evaluó; queda pendiente",
                )
            )
            resolved.append(
                ResolvedGate(
                    name=gate.name,
                    status=vocab.GateStatus.PENDING,
                    citation=None,
                    reason="el modelo no lo evaluó",
                )
            )
            continue

        reason = _clean(answer.reason) or NO_REASON
        if answer.status is vocab.GateStatus.PENDING:
            # Un filtro pendiente no se apoya en nada del anuncio: si algo
            # del anuncio lo resolviera, no estaría pendiente. La cita se
            # deja fuera en vez de guardar una que no sostiene el veredicto.
            resolved.append(
                ResolvedGate(
                    name=gate.name,
                    status=vocab.GateStatus.PENDING,
                    citation=None,
                    reason=reason,
                )
            )
            continue

        if not _quote_holds(answer.citation, acc):
            acc.corrections.append(
                Correction(
                    field=f"gates.{gate.name}",
                    rule="verdict_without_citation",
                    detail=(
                        "un filtro no se decide sin una cita que aparezca en el "
                        "anuncio; pasa a pendiente, que es lo único honesto "
                        "cuando no se pudo comprobar"
                    ),
                    previous=answer.status.value,
                    applied=vocab.GateStatus.PENDING.value,
                )
            )
            resolved.append(
                ResolvedGate(
                    name=gate.name,
                    status=vocab.GateStatus.PENDING,
                    citation=None,
                    reason=reason,
                )
            )
            continue

        resolved.append(
            ResolvedGate(
                name=gate.name,
                status=answer.status,
                citation=_clean(answer.citation),
                reason=reason,
            )
        )
    return tuple(resolved)


def _requirement_matches(
    draft: schemas.ScoringDraft,
    repo: DataRepo,
    requirement_positions: tuple[int, ...],
    acc: _Accumulator,
) -> tuple[ValidatedRequirementMatch, ...]:
    """El cruce de cada requisito contra el banco de bullets.

    Aquí es donde `enforce_match_rule`, escrita y probada en M1 sin datos,
    empieza a llamarse con datos de verdad. Y con la comprobación fuerte que
    en M1 no se podía hacer: no basta con que `evidence_ref` esté, tiene que
    **resolver** a un bullet que exista, esté `verified` y sea divulgable.
    Una referencia que no resuelve es exactamente el parecido de palabras
    que el contrato prohíbe, con la forma de un identificador.
    """
    seen: set[int] = set()
    matches = []
    for entry in draft.requirements:
        position = entry.requirement_index
        if position not in requirement_positions:
            acc.corrections.append(
                Correction(
                    field=f"requirements[{position}]",
                    rule="requirement_out_of_range",
                    detail=(
                        "el cruce apunta a un requisito que la extracción no "
                        "tiene; se descarta"
                    ),
                    previous=str(position),
                )
            )
            continue
        if position in seen:
            acc.corrections.append(
                Correction(
                    field=f"requirements[{position}]",
                    rule="duplicated_requirement_cross",
                    detail="venía cruzado dos veces; se guarda el primero",
                )
            )
            continue
        seen.add(position)

        reason = _clean(entry.reason) or NO_REASON
        reference = _clean(entry.evidence_ref) or None
        match = entry.match

        if reference is not None:
            bullet = repo.bullet(reference)
            if bullet is None:
                acc.corrections.append(
                    Correction(
                        field=f"requirements[{position}].evidence_ref",
                        rule="evidence_ref_does_not_resolve",
                        detail=(
                            "la referencia no existe en el banco de bullets; se "
                            "descarta la referencia"
                        ),
                        previous=reference,
                    )
                )
                reference = None
            elif not bullet.usable:
                acc.corrections.append(
                    Correction(
                        field=f"requirements[{position}].evidence_ref",
                        rule="evidence_ref_not_usable",
                        detail=(
                            f"«{reference}» existe pero está "
                            f"«{bullet.evidence_status}» con «{bullet.cv_usage}»: "
                            "no está comprobado o no es divulgable, así que no "
                            "sostiene una afirmación de cumplimiento"
                        ),
                        previous=reference,
                    )
                )
                reference = None

        # La regla de M1, tal cual: sin referencia, el máximo es `partial`.
        # No se reescribe aquí ni se duplica su lógica; se llama.
        match, correction = _enforced(position, match, reference)
        if correction is not None:
            acc.corrections.append(correction)

        matches.append(
            ValidatedRequirementMatch(
                requirement_position=position,
                match=match,
                evidence_ref=reference,
                reason=reason,
            )
        )
    return tuple(matches)


def _enforced(
    position: int,
    match: offers_vocab.RequirementMatch,
    reference: str | None,
) -> tuple[offers_vocab.RequirementMatch, Correction | None]:
    """La regla de M1, con el tipo estrechado.

    `enforce_match_rule` acepta y devuelve `None` porque en M1 el esquema
    del modelo no tenía `match` y la respuesta siempre era «nada». Aquí sí
    lo tiene, así que no puede salir `None`; el `or match` lo dice sin un
    `assert`, que en producción se ejecuta con `-O` y desaparece.
    """
    enforced, correction = enforce_match_rule(
        f"requirements[{position}].match", match, reference
    )
    return enforced or match, correction


def validate_scoring(
    draft: schemas.ScoringDraft,
    *,
    repo: DataRepo,
    raw_text: str,
    requirement_positions: tuple[int, ...],
) -> ValidatedScoring:
    """Comprueba una respuesta de scoring entera.

    Las infracciones se juntan y se lanzan todas de una vez, igual que en la
    extracción: si hay que cambiar el prompt, conviene verlas juntas en
    lugar de descubrirlas de una en una a base de reintentos que se pagan.
    """
    acc = _Accumulator(haystack=normalise(raw_text))
    model = repo.scoring

    probability_reason = _clean(draft.probability_reason)
    if not probability_reason:
        # No hay degradación honesta: la banda es un juicio, y un juicio sin
        # motivo no se puede enseñar ni discutir. Y al contrario que una
        # nota, no se puede dejar «sin puntuar»: la columna es obligatoria.
        acc.violations.append(
            "la banda de probabilidad viene sin motivo, y una banda sin motivo "
            "no se puede guardar"
        )

    dimensions = _dimensions(draft, model, acc)
    gates = _gates(draft, model, acc)
    matches = _requirement_matches(draft, repo, requirement_positions, acc)

    if acc.violations:
        raise AssessmentRejected(acc.violations)

    return ValidatedScoring(
        dimensions=dimensions,
        gates=gates,
        probability_band=draft.probability_band,
        probability_reason=probability_reason,
        requirement_matches=matches,
        corrections=tuple(acc.corrections),
    )


def validate_variant(
    draft: schemas.VariantChoiceDraft, *, variants: VariantGuide
) -> ValidatedVariant:
    """Comprueba que la variante elegida existe y viene motivada.

    Las dos son rechazo y no degradación. Elegir otra variante sería
    inventar una recomendación, y una recomendación sin motivo no sirve para
    lo que existe: `ARCHITECTURE.md` §7 dice que la app enseña *ese
    razonamiento* junto al PDF, y sin razonamiento no hay nada que enseñar.
    """
    violations = []
    variant = _clean(draft.variant)
    if variant not in variants.available:
        violations.append(
            f"«{variant or '(vacío)'}» no es una variante que exista; las que "
            f"hay son {list(variants.available)}"
        )
    reason = _clean(draft.reason)
    if not reason:
        violations.append("la variante elegida viene sin motivo")
    if violations:
        raise AssessmentRejected(violations)
    return ValidatedVariant(variant=variant, confidence=draft.confidence, reason=reason)
