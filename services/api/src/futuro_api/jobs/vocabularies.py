"""Vocabularios de la mitad operativa."""

from __future__ import annotations

from enum import StrEnum


class JobKind(StrEnum):
    """Tipos de trabajo encolado.

    Dos, y el segundo es el que valida el diseño de M1: `offer_assessment`
    hace **dos** llamadas al modelo —puntuar y elegir variante— y por eso
    `job_runs` y `llm_calls` son dos tablas y no una. El coste por propósito
    sale de `llm_calls.purpose`; la ejecución, de esta fila.
    """

    OFFER_EXTRACTION = "offer_extraction"
    OFFER_ASSESSMENT = "offer_assessment"


# Qué tarea del worker ejecuta cada tipo de trabajo.
#
# Son cadenas y no referencias a las funciones, y el motivo es concreto:
# `queue.py` necesita el nombre para encolar y `tasks.py` necesita encolar
# —la extracción encadena la puntuación— así que importarse mutuamente daba
# un ciclo. El vocabulario de tipos es el sitio natural para el mapa, porque
# no importa nada.
#
# Que estas cadenas sigan siendo los nombres reales de las funciones lo ata
# `tests/test_jobs.py`: arq registra cada tarea por su `__name__`, así que
# renombrar una función sin tocar esto encolaría un trabajo que nadie sabe
# ejecutar.
TASK_OF: dict[JobKind, str] = {}


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LlmCallStatus(StrEnum):
    """Estado de una llamada concreta al proveedor.

    `REFUSED` es un estado propio y no un fallo: con structured outputs el
    modelo puede negarse a responder, y eso no es un error de red ni un
    esquema mal formado. Confundirlos haría que un rechazo se reintentara
    para siempre.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUSED = "refused"


TASK_OF.update(
    {
        JobKind.OFFER_EXTRACTION: "extract_offer",
        JobKind.OFFER_ASSESSMENT: "assess_offer",
    }
)
