"""Lo que el modelo devuelve, antes de que el código lo valide.

Este módulo describe la **forma** de la respuesta, no su verdad. Todo lo que
hay aquí puede venir mal: un `source_quote` inventado, un `absent` con valor,
una cita que no está en el anuncio. De eso se ocupa `rules.py`.

El esquema está escrito para *structured outputs* en modo estricto, que
impone tres cosas: ningún campo tiene valor por defecto (todos son
obligatorios, y lo que puede faltar se declara anulable), ningún objeto
admite propiedades extra, y no se usan restricciones que el modo estricto no
soporta —`minLength`, `pattern`, `format`—. Por eso los mínimos y los
formatos se comprueban en `rules.py` y no aquí.

Lo que este esquema deja fuera a propósito es tan importante como lo que
tiene:

- `status_checked_at` no está. Lo pone el código, y en M1 no hay nada que
  compruebe el estado de un anuncio pegado, así que `active_verified` es
  inalcanzable por construcción y no por validación.
- `match`, `evidence_ref` y `cv_action` no están. Cruzar un requisito contra
  el banco de evidencias exige leer el repositorio privado, que es M3: al
  modelo no se le pregunta algo que no puede saber. No poder decirlo es más
  fuerte que decirlo y que el código lo tache.
- `deadline` no está: es dato de la captura, que lo pone Pablo.
- La capa `assessment` entera no está: es M2.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from futuro_api.offers import vocabularies as vocab

# `extra="forbid"` en todos los modelos: es lo que hace que el esquema
# generado lleve `additionalProperties: false`, que el modo estricto exige.
_STRICT = ConfigDict(extra="forbid")


class Evidence(BaseModel):
    """El sobre que acompaña a cada campo.

    Los tres campos opcionales están siempre presentes en la respuesta y
    valen `null` cuando no aplican, porque el modo estricto no permite
    omitir propiedades. Qué combinación es válida lo decide `rules.py`:
    `published` obliga a `source_quote`, `inferred` obliga a `reasoning` y
    `confidence`, y `absent` no admite ninguno.
    """

    model_config = _STRICT

    status: vocab.EvidenceStatus
    source_quote: str | None
    reasoning: str | None
    confidence: vocab.Confidence | None


class Claim[T](BaseModel):
    """Un valor y la evidencia que lo sostiene.

    `value` es anulable porque un campo `absent` no tiene valor. Un `value`
    no nulo con `status: absent` es contradictorio y `rules.py` lo rechaza:
    es la forma que tomaría rellenar un hueco con una estimación de mercado.
    """

    model_config = _STRICT

    value: T | None
    evidence: Evidence


class Identification(BaseModel):
    model_config = _STRICT

    title: Claim[str]
    role_family: Claim[vocab.RoleFamily]
    seniority_label: Claim[vocab.SeniorityLabel]
    # Si el anuncio pide una horquilla ("3-5 años"), el requisito es el
    # mínimo. Lo dice el prompt y lo repite este comentario porque es la
    # clase de decisión que alguien deshace sin darse cuenta.
    experience_years_required: Claim[float]
    location: Claim[str]
    work_mode: Claim[vocab.WorkMode]
    hiring_regions: Claim[list[str]]
    language_of_work: Claim[list[str]]
    contract_vehicle: Claim[vocab.ContractVehicle]
    posting_status: Claim[vocab.PostingStatus]


class Compensation(BaseModel):
    """Solo lo publicado.

    Tanto detalle porque una horquilla sin saber si es base o total, si el
    bonus es objetivo o máximo, y si la cifra se localiza al país de
    contratación, no se puede puntuar. Un único campo `salary` perdería
    justamente lo que hace falta.
    """

    model_config = _STRICT

    amount_min: Claim[float]
    amount_max: Claim[float]
    currency: Claim[str]
    period: Claim[vocab.CompensationPeriod]
    basis: Claim[vocab.CompensationBasis]
    bonus_pct: Claim[float]
    bonus_type: Claim[vocab.BonusType]
    equity: Claim[str]
    territorial_adjustment: Claim[vocab.TerritorialAdjustment]


class Companies(BaseModel):
    """Quien publica y el empleador final, separados.

    `employer_confidence` va fuera del sobre de `employer` porque tiene un
    valor que la confianza de un campo cualquiera no tiene: `confirmed`,
    para cuando quien publica es el propio empleador y por tanto no hay
    inferencia ninguna.
    """

    model_config = _STRICT

    posting: Claim[str]
    employer: Claim[str]
    employer_confidence: vocab.EmployerConfidence | None


class Requirement(BaseModel):
    model_config = _STRICT

    text: str
    source_quote: str
    kind: vocab.RequirementKind
    category: vocab.RequirementCategory


class Anomaly(BaseModel):
    """Un requisito imposible o mal configurado, con su explicación.

    `requirement_index` apunta a la posición en `requirements` en vez de
    repetir el texto: así el enlace se puede comprobar —un índice fuera de
    rango es una respuesta inventada— en lugar de adivinarlo cruzando
    cadenas. Es nulo cuando la anomalía es del anuncio entero.
    """

    model_config = _STRICT

    requirement_index: int | None
    text: str
    explanation: str
    source_quote: str


class ExtractionDraft(BaseModel):
    """La respuesta completa del modelo para una oferta."""

    model_config = _STRICT

    identification: Identification
    compensation: Compensation
    companies: Companies
    responsibilities: Claim[list[str]]
    requirements: list[Requirement]
    anomalies: list[Anomaly]
