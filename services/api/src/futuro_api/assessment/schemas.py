"""Lo que el modelo devuelve al puntuar, antes de que el código lo valide.

Igual que en la extracción, este módulo describe la **forma** de la
respuesta y no su verdad: una nota sin cita, una cita inventada o un filtro
dado por superado sin comprobar caben aquí y los caza `rules.py`.

Lo que este esquema **no** tiene es lo que más importa, y es la aplicación
literal del encargo «el código nunca acepta un `value_score` que venga
calculado por el modelo, aunque lo mande»:

- no hay `value_score`, ni `coverage`, ni `portfolio_bucket`, ni
  `effort_tier`, ni `unscored_dimensions`. Los calcula el código, así que no
  se le preguntan. Con `extra="forbid"` mandarlos no es «un campo que el
  código ignora»: es una respuesta que no parsea.
- no hay peso de dimensión. El peso lo pone `scoring_model.yaml`, y dejar
  que el modelo lo repita sería darle una segunda oportunidad de cambiarlo.

Es el mismo patrón que hizo `active_verified` inalcanzable en M1: no poder
decirlo es más fuerte que decirlo y que el código lo tache.

El esquema está escrito para *structured outputs* en modo estricto: ningún
campo con valor por defecto, ningún objeto con propiedades extra, y ninguna
restricción que el modo estricto no soporte. Los mínimos de longitud se
comprueban en `rules.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from futuro_api.assessment import vocabularies as vocab
from futuro_api.data_repo import vocabularies as data_vocab
from futuro_api.offers import vocabularies as offers_vocab

_STRICT = ConfigDict(extra="forbid")


class DimensionScore(BaseModel):
    """La nota de una dimensión, con lo que la sostiene.

    `dimension` es texto libre y no un enum porque la lista de dimensiones
    vive en `config/scoring_model.yaml` y cambia sin pasar por aquí.
    `rules.py` comprueba que el nombre es una de las dimensiones cargadas y
    descarta las que no lo son.

    `score` es anulable, y eso es lo que permite que el modelo diga «esta no
    la puedo puntuar» en vez de inventarse un número. Un `score` sin
    `citation` no es un error del modelo que se corrija: es una nota que no
    entra, y la dimensión queda sin puntuar.
    """

    model_config = _STRICT

    dimension: str
    score: int | None
    citation: str | None
    reason: str


class GateVerdict(BaseModel):
    """El estado de un filtro eliminatorio.

    `citation` es obligatoria para un veredicto que decide —`pass`, `fail`,
    `stretch`— y sobra para `pending`. Lo comprueba `rules.py`, que degrada
    a `pending` lo que no se puede sostener.
    """

    model_config = _STRICT

    gate: str
    status: vocab.GateStatus
    citation: str | None
    reason: str


class RequirementCross(BaseModel):
    """El cruce de un requisito contra el banco de evidencias.

    `requirement_index` apunta a la posición del requisito en la extracción
    en vez de repetir su texto, por el mismo motivo que en las anomalías de
    M1: un índice se puede comprobar y cruzar cadenas es adivinar.

    `evidence_ref` es un `bullet_id` del banco de bullets. `rules.py` no se
    conforma con que esté: comprueba que **resuelve** a un bullet que
    existe, está `verified` y es divulgable. Sin eso, el máximo que se puede
    afirmar es `partial`, que es la prohibición central del contrato.

    No hay `cv_action`: la adaptación fina por vacante está explícitamente
    fuera del diseño (`ARCHITECTURE.md` §7), así que nadie consumiría
    `include`/`prioritise`/`omit` y un campo que nadie lee se llena mal sin
    que nadie se entere. La columna existe; se queda nula.
    """

    model_config = _STRICT

    requirement_index: int
    match: offers_vocab.RequirementMatch
    evidence_ref: str | None
    reason: str


class ScoringDraft(BaseModel):
    """La respuesta completa del modelo al puntuar una oferta.

    El cruce de requisitos va aquí y no en una llamada aparte porque esta
    llamada ya lleva en contexto los requisitos de la extracción y el banco
    de bullets —los necesita para puntuar el encaje de rol—, así que
    separarlo sería pagar el mismo contexto dos veces.
    """

    model_config = _STRICT

    dimensions: list[DimensionScore]
    gates: list[GateVerdict]
    requirements: list[RequirementCross]
    probability_band: data_vocab.ProbabilityBand
    probability_reason: str


class VariantChoiceDraft(BaseModel):
    """La variante de CV elegida.

    El modelo **elige**, no redacta: `variant` tiene que ser uno de los
    identificadores de las variantes que existen en el repositorio de datos,
    y `rules.py` rechaza la recomendación si no lo es. No hay degradación
    honesta posible —elegir otra sería inventar— así que no se guarda nada.

    Sin `citation`: la elección es un juicio contra la guía de variantes, no
    un hecho publicado en el anuncio. Lo que se exige es el motivo.
    """

    model_config = _STRICT

    variant: str
    confidence: offers_vocab.Confidence
    reason: str
