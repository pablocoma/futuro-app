"""Donde el código valida lo que el modelo eligió.

El principio es el mismo que en `cv_builder`: **el LLM elige y cita, el
código valida**. Nada de lo que devuelve el modelo llega a la base de datos
sin pasar por aquí, y este módulo no confía en ninguna de sus afirmaciones.

Hay tres clases de respuesta a un incumplimiento, y la diferencia importa:

1. **Rechazo.** El modelo afirmó algo que no se puede guardar sin inventar
   —una cita que no dio, un valor sin evidencia— y no hay degradación
   honesta posible. Se lanza `ExtractionRejected` y no se guarda nada: es
   mejor no tener extracción que tener una que miente.
2. **Degradación.** El contrato dice qué vale como máximo cuando falta algo:
   sin `evidence_ref` el máximo es `partial`, sin comprobación de estado el
   máximo es `unverifiable`. Se aplica el máximo y se registra.
3. **Descarte del campo.** La afirmación no se sostiene pero el resto de la
   extracción sí: una cita que no aparece en el anuncio, un importe
   negativo. El campo pasa a `absent` —que es lo único honesto que se puede
   decir— y se registra.

Las degradaciones y los descartes se acumulan en `corrections`, que se
guarda con la extracción y se pinta en pantalla. No es un log: es la cuenta
de cuántas veces el modelo se salta las reglas, y sirve para decidir si el
prompt o el modelo hay que cambiarlos.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from futuro_api.offers import schemas
from futuro_api.offers import vocabularies as vocab

# Una cita más corta que esto no es una cita: encaja en cualquier texto y no
# sostiene nada. Tres caracteres deja pasar "SQL" o "C#", que sí son citas
# legítimas de un requisito de tecnología.
MIN_QUOTE_CHARS = 3

# Cuánto de una cita inventada se guarda en la corrección. Lo suficiente
# para reconocerla, no tanto como para duplicar el anuncio.
MAX_QUOTE_IN_CORRECTION = 120

# Comillas y guiones tipográficos que un modelo cambia sin darse cuenta al
# copiar. Normalizarlos evita descartar citas correctas por un carácter que
# nadie ve.
_LOOKALIKES = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "′": "'",
        "–": "-",
        "—": "-",
        "−": "-",
    }
)


def normalise(text: str) -> str:
    """Forma comparable de un texto: sin ruido de transcripción.

    Se aplica a la cita y al anuncio antes de compararlos. Perdona lo que
    un modelo cambia al copiar —espacios, saltos de línea, comillas
    curvas, mayúsculas— y no perdona nada más: si tras normalizar la cita
    no está en el anuncio, es que no está.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_LOOKALIKES)
    return " ".join(folded.split()).casefold()


class ExtractionRejected(Exception):
    """El modelo devolvió algo que no se puede guardar sin inventar."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("; ".join(violations))


@dataclass(frozen=True)
class Correction:
    """Algo que el código le corrigió al modelo.

    `rule` es un identificador estable para poder contar por regla; `detail`
    es para leer.
    """

    field: str
    rule: str
    detail: str
    previous: str | None = None
    applied: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "field": self.field,
            "rule": self.rule,
            "detail": self.detail,
            "previous": self.previous,
            "applied": self.applied,
        }


@dataclass(frozen=True)
class ValidatedRequirement:
    position: int
    text: str
    source_quote: str
    kind: vocab.RequirementKind
    category: vocab.RequirementCategory
    match: vocab.RequirementMatch | None
    evidence_ref: str | None
    cv_action: vocab.CvAction | None


@dataclass(frozen=True)
class ValidatedAnomaly:
    position: int
    requirement_position: int | None
    text: str
    explanation: str
    source_quote: str


@dataclass(frozen=True)
class ValidatedExtraction:
    """Lo que se puede guardar, con la cuenta de lo que hubo que corregir.

    `columns` y `evidence` van con nombres de columna de
    `offer_extractions`, no con los nombres del esquema del modelo: la
    traducción entre las dos formas se hace aquí y no en el repositorio, que
    así no tiene que saber nada del modelo.
    """

    columns: dict[str, Any]
    evidence: dict[str, dict[str, Any]]
    corrections: list[dict[str, str | None]]
    requirements: tuple[ValidatedRequirement, ...] = ()
    anomalies: tuple[ValidatedAnomaly, ...] = ()
    posting_company_name: str | None = None
    employer_company_name: str | None = None
    employer_confidence: vocab.EmployerConfidence | None = None


@dataclass
class _Accumulator:
    """Estado que se va llenando durante la validación."""

    haystack: str
    violations: list[str] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)


def enforce_match_rule(
    field_name: str,
    match: vocab.RequirementMatch | None,
    evidence_ref: str | None,
) -> tuple[vocab.RequirementMatch | None, Correction | None]:
    """Sin `evidence_ref`, el máximo que se puede afirmar es `partial`.

    Es la prohibición central del contrato: el parecido de palabras no es
    evidencia. En M1 devuelve `(None, None)` siempre, porque el esquema del
    modelo no tiene `match` y por tanto no puede afirmar que cumple algo.
    La regla se escribe y se prueba ahora para que M2, que es cuando se
    empiezan a rellenar esos campos, la herede ya funcionando.
    """
    if match is vocab.RequirementMatch.MEETS and not evidence_ref:
        return vocab.RequirementMatch.PARTIAL, Correction(
            field=field_name,
            rule="meets_needs_evidence_ref",
            detail=(
                "se afirmó que el perfil cumple el requisito sin citar ninguna "
                "evidencia; sin referencia el máximo es «parcial»"
            ),
            previous=vocab.RequirementMatch.MEETS.value,
            applied=vocab.RequirementMatch.PARTIAL.value,
        )
    return match, None


def _quote_is_in_the_advert(quote: str, haystack: str) -> bool:
    return normalise(quote) in haystack


def _shorten(quote: str) -> str:
    if len(quote) <= MAX_QUOTE_IN_CORRECTION:
        return quote
    return quote[:MAX_QUOTE_IN_CORRECTION] + "…"


def _resolve_claim(
    column: str,
    claim: schemas.Claim[Any],
    acc: _Accumulator,
) -> tuple[Any, dict[str, Any]]:
    """Comprueba el sobre de un campo y devuelve `(valor, evidencia)`.

    La evidencia que sale queda normalizada a las claves que ese estado
    admite, así que un `absent` con una cita suelta se guarda como un
    `absent` limpio.
    """
    status = claim.evidence.status
    absent: dict[str, Any] = {"status": vocab.EvidenceStatus.ABSENT.value}

    if status is vocab.EvidenceStatus.ABSENT:
        if claim.value is not None:
            # La forma exacta que tomaría rellenar un hueco con una
            # estimación de mercado. No hay degradación posible: si el dato
            # no está en el anuncio, el valor no puede venir de ninguna
            # parte legítima.
            acc.violations.append(
                f"{column}: evidencia «absent» con un valor rellenado ({claim.value!r})"
            )
        return None, absent

    if claim.value is None:
        acc.violations.append(
            f"{column}: evidencia «{status.value}» sin valor; si no consta, "
            "el estado es «absent»"
        )
        return None, absent

    if status is vocab.EvidenceStatus.PUBLISHED:
        quote = (claim.evidence.source_quote or "").strip()
        if not quote:
            acc.violations.append(f"{column}: «published» sin cita del anuncio")
            return None, absent
        if len(normalise(quote)) < MIN_QUOTE_CHARS:
            acc.violations.append(
                f"{column}: la cita «{quote}» es demasiado corta para sostener nada"
            )
            return None, absent
        if not _quote_is_in_the_advert(quote, acc.haystack):
            # Aquí se cae la afirmación entera: la cita es la prueba, y una
            # prueba que no está en el anuncio no prueba nada. Lo único que
            # se puede decir con honestidad es que el dato no aparece.
            acc.corrections.append(
                Correction(
                    field=column,
                    rule="unverified_quote",
                    detail=(
                        "la cita no aparece en el anuncio, así que el dato no "
                        "está publicado"
                    ),
                    previous=_shorten(quote),
                    applied=vocab.EvidenceStatus.ABSENT.value,
                )
            )
            return None, absent
        return claim.value, {
            "status": vocab.EvidenceStatus.PUBLISHED.value,
            "source_quote": quote,
        }

    # inferred
    reasoning = (claim.evidence.reasoning or "").strip()
    missing = []
    if not reasoning:
        missing.append("reasoning")
    if claim.evidence.confidence is None:
        missing.append("confidence")
    if missing:
        acc.violations.append(f"{column}: «inferred» sin {' ni '.join(missing)}")
        return None, absent
    assert claim.evidence.confidence is not None  # lo acaba de comprobar
    return claim.value, {
        "status": vocab.EvidenceStatus.INFERRED.value,
        "reasoning": reasoning,
        "confidence": claim.evidence.confidence.value,
    }


# Columnas que la base de datos guarda como NUMERIC y que el esquema del
# modelo declara como `number`, porque el modo estricto no admite decimales.
_NUMERIC_COLUMNS = (
    "experience_years_required",
    "comp_amount_min",
    "comp_amount_max",
    "comp_bonus_pct",
)


def _drop(
    column: str,
    columns: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    acc: _Accumulator,
    *,
    rule: str,
    detail: str,
    previous: str,
) -> None:
    """Descarta un campo dejándolo en `absent`, y lo registra."""
    columns[column] = None
    evidence[column] = {"status": vocab.EvidenceStatus.ABSENT.value}
    acc.corrections.append(
        Correction(
            field=column,
            rule=rule,
            detail=detail,
            previous=previous,
            applied=vocab.EvidenceStatus.ABSENT.value,
        )
    )


def _resolve_section(
    section: schemas.Identification | schemas.Compensation,
    prefix: str,
    columns: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    acc: _Accumulator,
) -> None:
    """Recorre los campos de una sección por reflexión, no por lista.

    Así añadir un campo al esquema no exige acordarse de añadirlo también
    aquí: si se olvidara, el campo se guardaría sin comprobar su evidencia,
    que es el fallo más caro posible en este módulo.
    """
    for name in type(section).model_fields:
        claim = getattr(section, name)
        column = f"{prefix}{name}"
        columns[column], evidence[column] = _resolve_claim(column, claim, acc)


def _clean_list(value: list[str]) -> list[str]:
    return [item.strip() for item in value if item and item.strip()]


def _apply_value_sanity(
    columns: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    acc: _Accumulator,
) -> None:
    """Descarta valores que no pueden ser lo que dicen ser.

    No son mentiras del modelo, son basura: un importe negativo, una moneda
    que no es un código ISO, una lista vacía presentada como dato. Se
    descartan en vez de rechazar la extracción entera, porque el resto de
    los campos siguen siendo buenos.
    """
    for column in _NUMERIC_COLUMNS:
        raw = columns.get(column)
        if raw is None:
            continue
        if raw < 0:
            _drop(
                column,
                columns,
                evidence,
                acc,
                rule="negative_number",
                detail="un valor negativo no es un dato de la oferta",
                previous=str(raw),
            )
            continue
        columns[column] = Decimal(str(raw))

    currency = columns.get("comp_currency")
    if currency is not None:
        code = str(currency).strip().upper()
        if len(code) == 3 and code.isalpha():
            columns["comp_currency"] = code
        else:
            _drop(
                "comp_currency",
                columns,
                evidence,
                acc,
                rule="not_a_currency_code",
                detail="la moneda no es un código ISO de tres letras",
                previous=str(currency),
            )

    for column in ("hiring_regions", "language_of_work", "responsibilities"):
        raw_list = columns.get(column)
        if raw_list is None:
            continue
        cleaned = _clean_list(list(raw_list))
        if cleaned:
            columns[column] = cleaned
        else:
            _drop(
                column,
                columns,
                evidence,
                acc,
                rule="empty_list",
                detail="una lista vacía no es un dato publicado",
                previous="[]",
            )

    # `responsibilities` es NOT NULL con `{}` por defecto: la ausencia se
    # representa con una lista vacía y no con un nulo, así que la columna se
    # normaliza aquí y su evidencia sigue diciendo `absent`.
    if columns.get("responsibilities") is None:
        columns["responsibilities"] = []

    low, high = columns.get("comp_amount_min"), columns.get("comp_amount_max")
    if low is not None and high is not None and low > high:
        # No se intenta arreglar intercambiándolos: no hay forma de saber
        # cuál de los dos está mal, y una horquilla invertida que se cuele
        # envenena el scoring de M2 en silencio.
        detail = "la horquilla está invertida y no se puede saber cuál sobra"
        _drop(
            "comp_amount_min",
            columns,
            evidence,
            acc,
            rule="inverted_range",
            detail=detail,
            previous=str(low),
        )
        _drop(
            "comp_amount_max",
            columns,
            evidence,
            acc,
            rule="inverted_range",
            detail=detail,
            previous=str(high),
        )


def _apply_posting_status_rule(columns: dict[str, Any], acc: _Accumulator) -> None:
    """`active_verified` exige una comprobación que en M1 no existe.

    Que el anuncio se describa como activo no es una comprobación: es una
    afirmación del anuncio. Y de un texto pegado no hay URL que consultar,
    así que no hay `status_checked_at` posible y el máximo honesto es
    `unverifiable`.
    """
    status = columns.get("posting_status")
    if status is None:
        # La columna es NOT NULL y `unverifiable` significa literalmente «no
        # se puede verificar», que es la verdad cuando el anuncio no dice
        # nada. No es una corrección: la evidencia sigue siendo `absent`.
        columns["posting_status"] = vocab.PostingStatus.UNVERIFIABLE
        return
    if status is vocab.PostingStatus.ACTIVE_VERIFIED:
        columns["posting_status"] = vocab.PostingStatus.UNVERIFIABLE
        acc.corrections.append(
            Correction(
                field="posting_status",
                rule="active_verified_needs_a_check",
                detail=(
                    "nadie ha comprobado que la oferta siga abierta, y que el "
                    "anuncio lo diga no es una comprobación"
                ),
                previous=vocab.PostingStatus.ACTIVE_VERIFIED.value,
                applied=vocab.PostingStatus.UNVERIFIABLE.value,
            )
        )


def _resolve_companies(
    draft: schemas.ExtractionDraft,
    evidence: dict[str, dict[str, Any]],
    acc: _Accumulator,
) -> tuple[str | None, str | None, vocab.EmployerConfidence | None]:
    """Los nombres de las dos empresas, cada uno con su evidencia.

    Devuelve nombres y no identificadores: resolver un nombre a una fila de
    `companies` es trabajo del repositorio. La evidencia se guarda con el
    nombre de la columna que acabará llevando el identificador, para que la
    pantalla pueda enseñar de dónde sale cada una.
    """
    posting_name, evidence["posting_company_id"] = _resolve_claim(
        "posting_company_id", draft.companies.posting, acc
    )
    employer_name, evidence["employer_company_id"] = _resolve_claim(
        "employer_company_id", draft.companies.employer, acc
    )
    confidence = draft.companies.employer_confidence

    if isinstance(posting_name, str):
        posting_name = posting_name.strip() or None
    if isinstance(employer_name, str):
        employer_name = employer_name.strip() or None

    if employer_name is None:
        if confidence is not None:
            acc.corrections.append(
                Correction(
                    field="employer_confidence",
                    rule="confidence_without_an_employer",
                    detail="no hay empleador final que respaldar con una confianza",
                    previous=confidence.value,
                    applied=None,
                )
            )
        return posting_name, None, None

    if confidence is None:
        # Registrar un empleador inferido sin decir con cuánta confianza es
        # exactamente registrarlo como un hecho, que es lo que el contrato
        # prohíbe. No hay degradación: `low` sería inventar la confianza.
        acc.violations.append(
            "employer_company_id: se nombra un empleador final sin "
            "`employer_confidence`"
        )
        return posting_name, employer_name, None

    if (
        posting_name is not None
        and normalise(posting_name) == normalise(employer_name)
        and confidence is not vocab.EmployerConfidence.CONFIRMED
    ):
        # Si quien publica es el propio empleador, no hay inferencia que
        # calibrar: lo dice el anuncio.
        acc.corrections.append(
            Correction(
                field="employer_confidence",
                rule="self_posted_employer_is_confirmed",
                detail="quien publica y el empleador son la misma empresa",
                previous=confidence.value,
                applied=vocab.EmployerConfidence.CONFIRMED.value,
            )
        )
        confidence = vocab.EmployerConfidence.CONFIRMED

    return posting_name, employer_name, confidence


def _resolve_requirements(
    draft: schemas.ExtractionDraft, acc: _Accumulator
) -> tuple[tuple[ValidatedRequirement, ...], dict[int, int]]:
    """Los requisitos que se sostienen, renumerados, y el mapa de índices.

    El mapa traduce el índice que usó el modelo a la posición final, porque
    descartar un requisito mueve a todos los siguientes y las anomalías
    apuntan al índice original.
    """
    resolved: list[ValidatedRequirement] = []
    index_map: dict[int, int] = {}

    for index, requirement in enumerate(draft.requirements):
        label = f"requirements[{index}]"
        text = requirement.text.strip()
        quote = requirement.source_quote.strip()
        if not text:
            acc.violations.append(f"{label}: requisito sin texto")
            continue
        if len(normalise(quote)) < MIN_QUOTE_CHARS:
            acc.violations.append(
                f"{label}: cita demasiado corta para sostener el requisito"
            )
            continue
        if not _quote_is_in_the_advert(quote, acc.haystack):
            # Un requisito cuya cita no está en el anuncio es un requisito
            # que nadie ha pedido. Se descarta en vez de degradarse: no hay
            # una versión más débil de «existe».
            acc.corrections.append(
                Correction(
                    field=label,
                    rule="unverified_quote",
                    detail="la cita no aparece en el anuncio; el requisito se descarta",
                    previous=_shorten(quote),
                    applied=None,
                )
            )
            continue

        # En M1 los tres campos del cruce llegan vacíos, porque el esquema
        # del modelo no los tiene. La regla se aplica igual, para que el día
        # que M2 los rellene no haya que acordarse de llamarla.
        match, correction = enforce_match_rule(f"{label}.match", None, None)
        if correction is not None:  # pragma: no cover - inalcanzable en M1
            acc.corrections.append(correction)

        position = len(resolved) + 1
        index_map[index] = position
        resolved.append(
            ValidatedRequirement(
                position=position,
                text=text,
                source_quote=quote,
                kind=requirement.kind,
                category=requirement.category,
                match=match,
                evidence_ref=None,
                cv_action=None,
            )
        )

    return tuple(resolved), index_map


def _resolve_anomalies(
    draft: schemas.ExtractionDraft,
    index_map: dict[int, int],
    acc: _Accumulator,
) -> tuple[ValidatedAnomaly, ...]:
    resolved: list[ValidatedAnomaly] = []

    for index, anomaly in enumerate(draft.anomalies):
        label = f"anomalies[{index}]"
        text = anomaly.text.strip()
        explanation = anomaly.explanation.strip()
        quote = anomaly.source_quote.strip()

        if not text or not explanation:
            acc.violations.append(f"{label}: anomalía sin texto o sin explicación")
            continue
        pointer = anomaly.requirement_index
        if pointer is not None and not 0 <= pointer < len(draft.requirements):
            # Un índice fuera de rango no se puede interpretar de ninguna
            # forma benigna: apunta a un requisito que no existe.
            acc.violations.append(
                f"{label}: apunta al requisito {pointer}, que no existe"
            )
            continue
        if len(normalise(quote)) < MIN_QUOTE_CHARS:
            acc.violations.append(f"{label}: cita demasiado corta")
            continue
        if not _quote_is_in_the_advert(quote, acc.haystack):
            acc.corrections.append(
                Correction(
                    field=label,
                    rule="unverified_quote",
                    detail="la cita no aparece en el anuncio; la anomalía se descarta",
                    previous=_shorten(quote),
                    applied=None,
                )
            )
            continue

        resolved.append(
            ValidatedAnomaly(
                position=len(resolved) + 1,
                # Nulo también cuando el requisito al que apuntaba se
                # descartó: la anomalía puede seguir siendo cierta del
                # anuncio aunque su requisito no se sostuviera.
                requirement_position=(
                    index_map.get(pointer) if pointer is not None else None
                ),
                text=text,
                explanation=explanation,
                source_quote=quote,
            )
        )

    return tuple(resolved)


def _flag_anomalies_without_explanation(
    requirements: tuple[ValidatedRequirement, ...],
    anomalies: tuple[ValidatedAnomaly, ...],
    acc: _Accumulator,
) -> None:
    """Un requisito marcado como anómalo tiene que venir explicado.

    Se registra en vez de rechazarse o de reetiquetar el requisito: la
    señal de que algo va mal en el anuncio sigue siendo útil para el filtro
    automático de M2 aunque el modelo no haya dicho por qué.
    """
    explained = {
        anomaly.requirement_position
        for anomaly in anomalies
        if anomaly.requirement_position is not None
    }
    for requirement in requirements:
        if requirement.kind is vocab.RequirementKind.ANOMALOUS:
            if requirement.position not in explained:
                acc.corrections.append(
                    Correction(
                        field=f"requirements[{requirement.position - 1}].kind",
                        rule="anomaly_without_explanation",
                        detail=(
                            "el requisito se marcó como anómalo pero ninguna "
                            "anomalía explica por qué"
                        ),
                        previous=vocab.RequirementKind.ANOMALOUS.value,
                        applied=vocab.RequirementKind.ANOMALOUS.value,
                    )
                )


def validate(draft: schemas.ExtractionDraft, raw_text: str) -> ValidatedExtraction:
    """Convierte la respuesta del modelo en algo que se puede guardar.

    Lanza `ExtractionRejected` si hay algo que no se puede guardar sin
    inventar, con **todas** las infracciones y no solo la primera: si el
    prompt o el modelo hay que cambiarlos, conviene verlas juntas.
    """
    acc = _Accumulator(haystack=normalise(raw_text))
    columns: dict[str, Any] = {}
    evidence: dict[str, dict[str, Any]] = {}

    _resolve_section(draft.identification, "", columns, evidence, acc)
    _resolve_section(draft.compensation, "comp_", columns, evidence, acc)
    columns["responsibilities"], evidence["responsibilities"] = _resolve_claim(
        "responsibilities", draft.responsibilities, acc
    )
    _apply_value_sanity(columns, evidence, acc)
    _apply_posting_status_rule(columns, acc)

    posting_name, employer_name, confidence = _resolve_companies(draft, evidence, acc)
    requirements, index_map = _resolve_requirements(draft, acc)
    anomalies = _resolve_anomalies(draft, index_map, acc)
    _flag_anomalies_without_explanation(requirements, anomalies, acc)

    if acc.violations:
        raise ExtractionRejected(acc.violations)

    return ValidatedExtraction(
        columns=columns,
        evidence=evidence,
        corrections=[correction.as_dict() for correction in acc.corrections],
        requirements=requirements,
        anomalies=anomalies,
        posting_company_name=posting_name,
        employer_company_name=employer_name,
        employer_confidence=confidence,
    )
