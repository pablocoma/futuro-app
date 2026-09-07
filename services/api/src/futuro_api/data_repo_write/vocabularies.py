"""Vocabularios de código para `cv/content/professional_bullet_bank.yaml`.

Ningún código comprobaba hasta ahora un juego cerrado de valores para
`evidence_status`/`cv_usage`: `data_repo/models.py` y `cv_builder` los
transportan como texto libre y solo comparan contra una constante concreta
(`verified`/`eligible_with_internal_policy_check`). Pero un typo en
cualquiera de los dos dejaría un bullet inalcanzable en silencio -el mismo
fallo que `RoleFamily` existe para atrapar en `objectives.yaml`-, así que
Fase 2 M2 sí los cierra al escribir.

Los valores de `evidence_status` son los que `profile/project_catalog.yaml`
ya documenta explícitamente para el mismo concepto
(`rules.allowed_evidence_statuses`), investigado el 2026-09-07. Los de
`cv_usage` son los observados en el propio banco de bullets -
`policy.default_cv_usage: blocked` y el valor real
`eligible_with_internal_policy_check`- más `conditional`, que
`project_catalog.yaml` usa para el mismo concepto con menos granularidad.

Fase 2 M3 añade `ProjectCvUsage`, para `cv_usage`/`interview_usage` de
`profile/project_catalog.yaml`. Investigado el 2026-09-07: ese fichero
documenta su propio vocabulario para el mismo nombre de campo
(`eligible_or_conditional_or_blocked`), distinto del de
`BulletCvUsage` (`eligible_with_internal_policy_check`, no `eligible`) -
son dos conceptos que comparten nombre de campo, no el mismo enum. En
cambio `evidence_status` de un proyecto sí reutiliza `BulletEvidenceStatus`
tal cual: mismos cuatro valores, y es precisamente el fichero del que M2
los tomó.
"""

from __future__ import annotations

from enum import StrEnum


class BulletEvidenceStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    PUBLISHABLE = "publishable"
    REJECTED = "rejected"


class BulletCvUsage(StrEnum):
    BLOCKED = "blocked"
    CONDITIONAL = "conditional"
    ELIGIBLE_WITH_INTERNAL_POLICY_CHECK = "eligible_with_internal_policy_check"


class ProjectCvUsage(StrEnum):
    ELIGIBLE = "eligible"
    CONDITIONAL = "conditional"
    BLOCKED = "blocked"
