"""Registro único de tablas.

Importar este módulo puebla `Base.metadata` con el esquema completo, y es lo
que tienen que importar Alembic y los tests.

Existe porque las dos mitades se referencian mutuamente:
`offer_extractions.job_run_id` apunta a `job_runs`, y `job_runs.capture_id`
apunta a `offer_captures`. Ninguno de los dos módulos puede importar al otro
sin un ciclo, así que el punto de reunión es este tercero. Importar solo una
mitad hace que SQLAlchemy no encuentre la tabla de la otra al configurar los
mapeos, y el error sale tarde: no al importar, sino la primera vez que
alguien usa el ORM.
"""

from __future__ import annotations

from futuro_api.jobs.models import JobRun, LlmCall
from futuro_api.offers.models import (
    Company,
    OfferAnomaly,
    OfferCapture,
    OfferExtraction,
    OfferRequirement,
)

__all__ = [
    "Company",
    "JobRun",
    "LlmCall",
    "OfferAnomaly",
    "OfferCapture",
    "OfferExtraction",
    "OfferRequirement",
]
