"""Los tres vocabularios del modelo de scoring sobre los que el código ramifica.

Aquí está la corrección a un supuesto que parecía razonable y no lo es. La
idea de partida era que **todo** vocabulario que vive en el repositorio de
datos fuese `text` sin CHECK, validado en Python contra lo cargado: una
migración no debe ir detrás de un YAML que se edita a mano.

Eso vale para los nombres de las dimensiones, los de los filtros y los
identificadores de variante: el código los transporta y no decide nada con
ellos. No vale para estos tres. Para calcular el cubo de cartera y el nivel
de esfuerzo hay que preguntar «¿es esta banda `high`?», así que renombrar
`high` en el YAML no rompería una constraint: cambiaría en silencio el
resultado de una comparación y todas las ofertas caerían en otro cubo sin
que nada avisara.

Así que estos tres sí son vocabulario de código, con su CHECK en la base de
datos, y el cargador comprueba al arrancar que el YAML declara exactamente
estos nombres. Si el repositorio de datos los renombra, el scoring se niega
a funcionar con un mensaje que lo dice, en vez de puntuar mal.

`config/scoring_model.yaml` no expresa las reglas en forma legible por
máquina —`realistic: probabilidad high y valor >= 3.0` es prosa— así que los
predicados y sus umbrales están en `assessment/scoring.py`, copiados a mano
con su fecha. Es la misma disciplina que `llm/cost.py` aplica a la tabla de
tarifas del proveedor, y por eso cada fila de assessment guarda el hash del
YAML con el que se puntuó.
"""

from __future__ import annotations

from enum import StrEnum


class ProbabilityBand(StrEnum):
    """Las cuatro bandas de `probability_bands`. Las pone el modelo."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class PortfolioBucket(StrEnum):
    """Los cinco cubos de `portfolio_assignment`. Los calcula el código."""

    REALISTIC = "realistic"
    REALISTIC_STRETCH = "realistic_stretch"
    ASPIRATIONAL = "aspirational"
    EXPERIMENTAL = "experimental"
    DISCARD = "discard"


class EffortTier(StrEnum):
    """Los cuatro niveles de `output.effort_tier`. Los calcula el código.

    El orden de evaluación no es este: lo declara el YAML
    (`evaluation_order`) y el código lo respeta tal cual, porque el YAML
    manda. Ver `assessment/scoring.py`.
    """

    FULL = "full"
    STANDARD = "standard"
    CHEAP = "cheap"
    SKIP = "skip"
