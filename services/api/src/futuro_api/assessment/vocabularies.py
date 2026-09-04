"""Vocabularios de la capa `assessment` que son de código.

Los que vienen del repositorio de datos —bandas, cubos y niveles de
esfuerzo— están en `data_repo/vocabularies.py`, con la explicación de por
qué esos tres no pueden ser libres. Los nombres de dimensión, de filtro y
de variante no tienen enum en ninguna parte: son `text`, y el vocabulario
válido es el que el YAML declara en cada momento.
"""

from __future__ import annotations

from enum import StrEnum


class GateStatus(StrEnum):
    """El estado de un filtro eliminatorio.

    Los pone el modelo y el código los degrada cuando no se sostienen.
    `PENDING` es el valor al que se degrada todo lo que no se puede
    comprobar, nunca `FAIL`: «no consta» no es «incumple». Lo dice
    `scoring_model.yaml`: «Un filtro que no puede evaluarse queda
    'pending'. Nunca se supone superado».

    `STRETCH` existe porque el YAML lo declara en `plausible_seniority`,
    donde un requisito de tres años no descarta si el encaje compensa.
    """

    PASS = "pass"
    STRETCH = "stretch"
    PENDING = "pending"
    FAIL = "fail"


class AssessmentSource(StrEnum):
    """De dónde sale una fila de assessment.

    Es la columna que hace comprobable la propiedad que justifica que
    `assessment` sea una capa aparte: una fila `RECOMPUTED` no tiene ni
    `job_run_id` ni llamadas al modelo asociadas, y el test de repuntuación
    lo comprueba exactamente así.
    """

    LLM = "llm"
    RECOMPUTED = "recomputed"
