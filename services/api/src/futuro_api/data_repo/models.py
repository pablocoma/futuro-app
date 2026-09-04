"""La forma de lo que se lee del repositorio privado.

Objetos de solo lectura: desde esta aplicación el repositorio privado **solo
se lee**. Nada de este paquete escribe, hace commit ni toca git.

Cada pieza guarda el `sha256` del fichero del que salió. No es decorativo:
`config/scoring_model.yaml` declara `version: 1` y el propio contrato cuenta
que el modelo cambió dos veces el mismo día, así que fiarse solo del número
declarado es fiarse de que alguien se acuerde de subirlo. Con el hash, dos
ofertas puntuadas con textos distintos del mismo `version` se distinguen.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

# Estados del banco de bullets que hacen que una evidencia sostenga un
# `meets`. Los dos, no uno: `verified` dice que el contenido está
# comprobado, y `cv_usage` dice que además se puede divulgar. Son los
# mismos que `cv_builder.claim_rules` exige para meter un bullet en un CV,
# y por el mismo motivo.
USABLE_EVIDENCE_STATUS = "verified"
USABLE_CV_USAGE = "eligible_with_internal_policy_check"


@dataclass(frozen=True)
class Dimension:
    """Una dimensión del eje de valor, con su peso y sus anclas."""

    name: str
    weight: int
    # Las anclas escritas, por nota. El YAML define 0, 1, 3 y 5; el 2 y el 4
    # se interpolan, así que no tienen texto.
    anchors: dict[int, str]
    # `measured_against`, `assumption`, `note`, `includes`… tal cual vengan.
    # No se interpretan: viajan al prompt para que el modelo puntúe con la
    # misma referencia que usaría Pablo.
    notes: dict[str, str]

    def anchor_for(self, score: int) -> str | None:
        """El ancla escrita que aplica a una nota.

        La exacta si existe, y si no la más alta por debajo: un 4 se explica
        con el ancla del 3, que es lo que significa interpolar. Devuelve
        `None` si no hay ninguna por debajo, que solo pasa con un YAML sin
        ancla del 0.
        """
        applicable = [level for level in sorted(self.anchors) if level <= score]
        return self.anchors[applicable[-1]] if applicable else None


@dataclass(frozen=True)
class Gate:
    """Un filtro eliminatorio, con lo que el YAML escribe de él.

    `criteria` son las claves que describen cuándo el filtro vale qué, tal
    como vengan: `pass`, `fail`, `pending`, `stretch`, y también las
    variantes que el YAML use por su cuenta —`pass_spain`, `pass_abroad`—.
    El código no ramifica sobre ellas; se le pasan al modelo como guía y es
    él quien responde con uno de los cuatro estados de
    `assessment.vocabularies.GateStatus`.
    """

    name: str
    criteria: dict[str, str]
    notes: dict[str, str]


@dataclass(frozen=True)
class ScoringModel:
    """`config/scoring_model.yaml`, ya validado."""

    version: str
    updated_at: str
    sha256: str
    # El bloque `baseline_*` tal cual. Va al prompt porque sin la referencia
    # económica la dimensión de ahorro no se puede puntuar contra nada.
    baseline_name: str
    baseline: dict[str, Any]
    dimensions: tuple[Dimension, ...]
    score_min: int
    score_max: int
    gates: tuple[Gate, ...]
    probability_bands: dict[str, str]
    portfolio_buckets: dict[str, str]
    effort_tiers: dict[str, dict[str, str]]
    effort_evaluation_order: tuple[str, ...]
    minimum_coverage: Decimal
    # La prohibición de estimar, literal. Se le repite al modelo en el
    # prompt: es la que convierte «no lo sé» en la respuesta correcta.
    never_rule: str

    @property
    def total_weight(self) -> int:
        return sum(dimension.weight for dimension in self.dimensions)

    @property
    def dimension_names(self) -> tuple[str, ...]:
        return tuple(dimension.name for dimension in self.dimensions)

    @property
    def gate_names(self) -> tuple[str, ...]:
        return tuple(gate.name for gate in self.gates)

    def dimension(self, name: str) -> Dimension | None:
        return next((d for d in self.dimensions if d.name == name), None)


@dataclass(frozen=True)
class VariantGuide:
    """Las variantes de CV que existen, y la guía que el modelo lee.

    `available` son los directorios que **existen** bajo `cv/variants/` y
    que además están declarados en `config/cv_variants.yaml`. Sale del disco
    y no del YAML a propósito: el YAML declara variantes que todavía no se
    generan, y una variante sin documento no se puede elegir. Así «elige
    entre los documentos que ya existen» es una propiedad del vocabulario y
    no un ruego en el prompt.
    """

    guide_text: str
    guide_sha256: str
    available: tuple[str, ...]
    declared: frozenset[str]

    @property
    def declared_but_missing(self) -> tuple[str, ...]:
        """Declaradas y sin carpeta. Diagnóstico, no error."""
        return tuple(sorted(self.declared - set(self.available)))


@dataclass(frozen=True)
class Bullet:
    """Una evidencia del banco de bullets.

    `usable` es lo que decide si puede sostener un `meets`. Un bullet
    `candidate`, o `verified` pero con `cv_usage: blocked`, existe y se
    puede citar en el razonamiento, pero no vale como referencia: el
    contrato prohíbe afirmar que el perfil cumple algo apoyándose en una
    evidencia que no está comprobada o que no se puede divulgar.
    """

    bullet_id: str
    text: str
    evidence_status: str
    cv_usage: str
    role_families: tuple[str, ...]

    @property
    def usable(self) -> bool:
        return (
            self.evidence_status == USABLE_EVIDENCE_STATUS
            and self.cv_usage == USABLE_CV_USAGE
        )


@dataclass(frozen=True)
class DisqualifyingCondition:
    """Una condición de `constraints.yaml` que descarta una oferta."""

    id: str
    rule: str


@dataclass(frozen=True)
class DataRepo:
    """Todo lo que la aplicación necesita del repositorio privado.

    Se carga entero de una vez y se trata como inmutable. Cargarlo pieza a
    pieza dejaría abierta la posibilidad de puntuar una oferta con un modelo
    de scoring y elegir variante con una guía de otro momento.
    """

    root: Path
    scoring: ScoringModel
    core_role_families: frozenset[str]
    disqualifying_conditions: tuple[DisqualifyingCondition, ...]
    variants: VariantGuide
    bullets: tuple[Bullet, ...]

    def bullet(self, bullet_id: str) -> Bullet | None:
        return next((b for b in self.bullets if b.bullet_id == bullet_id), None)

    @property
    def usable_bullets(self) -> tuple[Bullet, ...]:
        return tuple(bullet for bullet in self.bullets if bullet.usable)
