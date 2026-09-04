"""Registro único de tablas.

Importar este módulo puebla `Base.metadata` con el esquema completo, y es lo
que tienen que importar Alembic y los tests.

Existe porque las mitades se referencian entre sí:
`offer_extractions.job_run_id` apunta a `job_runs`, `job_runs.capture_id`
apunta a `offer_captures`, y las tablas de `assessment` apuntan a las dos.
Ninguno de esos módulos puede importar a los demás sin un ciclo, así que el
punto de reunión es este tercero. Importar solo una parte hace que
SQLAlchemy no encuentre las tablas del resto al configurar los mapeos, y el
error sale tarde: no al importar, sino la primera vez que alguien usa el
ORM.
"""

from __future__ import annotations

from futuro_api.assessment.models import (
    AssessmentDimension,
    AssessmentGate,
    OfferAssessment,
    RequirementMatchRow,
    VariantRecommendation,
)
from futuro_api.jobs.models import JobRun, LlmCall
from futuro_api.offers.models import (
    Company,
    OfferAnomaly,
    OfferCapture,
    OfferExtraction,
    OfferRequirement,
)

__all__ = [
    "AssessmentDimension",
    "AssessmentGate",
    "Company",
    "JobRun",
    "LlmCall",
    "OfferAnomaly",
    "OfferAssessment",
    "OfferCapture",
    "OfferExtraction",
    "OfferRequirement",
    "RequirementMatchRow",
    "VariantRecommendation",
]
