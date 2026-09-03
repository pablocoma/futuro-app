"""Vocabularios cerrados del contrato de datos de una oferta.

Un solo sitio para cada lista de valores: de aquí salen a la vez el tipo de
columna (VARCHAR con CHECK, ver `models.py`) y el esquema que se le pasa al
modelo. Si divergieran, el modelo podría devolver un valor que la base de
datos rechaza en el último momento, y el error saldría en el sitio menos
útil.

Los valores son los del contrato salvo dos, que el contrato nombra sin
cerrar: `CompensationPeriod` y `TerritorialAdjustment`. Se cierran aquí
porque un campo abierto no se puede validar; queda pendiente reflejarlo en
el contrato del repositorio privado, donde no escribimos desde aquí.
"""

from __future__ import annotations

from enum import StrEnum


class SourceChannel(StrEnum):
    """Los cinco canales del contrato.

    La columna acepta los cinco, pero en M1 el endpoint solo admite `PASTE`:
    la restricción es del canal, no del esquema.
    """

    PASTE = "paste"
    URL = "url"
    EXTENSION = "extension"
    TELEGRAM = "telegram"
    EMAIL = "email"


class EvidenceStatus(StrEnum):
    """La regla transversal: todo campo de `extraction` lleva uno de estos."""

    PUBLISHED = "published"
    INFERRED = "inferred"
    ABSENT = "absent"


class Confidence(StrEnum):
    """Confianza de un campo `inferred`.

    Escala cerrada y no un número entre 0 y 1: los modelos no calibran
    probabilidades, y un `0.83` es precisión falsa.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EmployerConfidence(StrEnum):
    """Confianza en la inferencia del empleador final.

    Tiene `CONFIRMED`, que `Confidence` no tiene: cuando quien publica es el
    propio empleador, el dato está confirmado y no inferido.
    """

    CONFIRMED = "confirmed"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RoleFamily(StrEnum):
    """Las siete familias core de `config/objectives.yaml`, más dos."""

    AI_ENGINEER = "ai_engineer"
    MACHINE_LEARNING_ENGINEER = "machine_learning_engineer"
    DATA_SCIENTIST = "data_scientist"
    DATA_AI_CONSULTANT = "data_ai_consultant"
    SOLUTIONS_ENGINEER = "solutions_engineer"
    FORWARD_DEPLOYED_ENGINEER = "forward_deployed_engineer"
    DATA_ENGINEER = "data_engineer"
    QUANTITATIVE_ROLES = "quantitative_roles"
    OTHER = "other"


class SeniorityLabel(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    LEAD = "lead"
    UNSPECIFIED = "unspecified"


class WorkMode(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


class ContractVehicle(StrEnum):
    EMPLOYMENT = "employment"
    EOR = "eor"
    B2B = "b2b"
    UNKNOWN = "unknown"


class PostingStatus(StrEnum):
    """Estado del anuncio.

    `ACTIVE_VERIFIED` exige `status_checked_at`, y en M1 no hay nada que
    compruebe el estado de una URL que no tenemos: de un texto pegado el
    código nunca acepta ese valor.
    """

    ACTIVE_VERIFIED = "active_verified"
    EXPIRED = "expired"
    UNVERIFIABLE = "unverifiable"


class CompensationPeriod(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    UNCLEAR = "unclear"


class CompensationBasis(StrEnum):
    BASE = "base"
    TOTAL = "total"
    UNCLEAR = "unclear"


class BonusType(StrEnum):
    TARGET = "target"
    MAX = "max"
    DISCRETIONARY = "discretionary"
    UNCLEAR = "unclear"


class TerritorialAdjustment(StrEnum):
    """Si la cifra publicada se localiza al país de contratación.

    Existe porque una horquilla sin saber si se ajusta al territorio no se
    puede puntuar, y `unclear` es una respuesta legítima y frecuente.
    """

    LOCALISED = "localised"
    NOT_LOCALISED = "not_localised"
    UNCLEAR = "unclear"


class RequirementKind(StrEnum):
    MANDATORY = "mandatory"
    DESIRABLE = "desirable"
    ANOMALOUS = "anomalous"


class RequirementCategory(StrEnum):
    TECHNOLOGY = "technology"
    EXPERIENCE_YEARS = "experience_years"
    DOMAIN = "domain"
    AUTONOMY = "autonomy"
    LANGUAGE = "language"
    EDUCATION = "education"
    OTHER = "other"


class RequirementMatch(StrEnum):
    """Cruce del requisito contra el banco de evidencias.

    En M1 se queda en NULL en todas las filas: cruzar exige leer el
    repositorio privado, y ese clon es M3. NULL significa «sin evaluar», que
    no es lo mismo que `NO_EVIDENCE`, «evaluado y no hay nada».
    """

    MEETS = "meets"
    PARTIAL = "partial"
    NO_EVIDENCE = "no_evidence"


class CvAction(StrEnum):
    INCLUDE = "include"
    PRIORITISE = "prioritise"
    OMIT = "omit"
