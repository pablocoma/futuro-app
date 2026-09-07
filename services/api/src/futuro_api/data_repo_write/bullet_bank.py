"""`cv/content/professional_bullet_bank.yaml`, Fase 2 M2.

Mismo mecanismo que `objectives.py`/`preferences.py`/`constraints.py`
-`current`/`prepare`/`write`, revalida el documento entero tras aplicar la
edición-. Lo que es propio de este fichero:

**Solo `text_en`, `evidence_status` y `cv_usage` son editables por fila**
-alcance confirmado con Pablo el 2026-09-07-. `bullet_id` casa cada
edición contra la fila existente, igual que `disqualifying_conditions.id`
en M1; un `bullet_id` que no exista se añade como fila nueva, con el resto
de sus campos (`bullet_type`, `project_id`, `angle`, `role_variants`,
`blocked_by`) a valores por defecto seguros -sin fabricar una
`confidentiality_status` que no se ha confirmado de verdad-. Sin borrado:
esta rebanada no ofrece ningún camino para pedirlo.

**Las `claim_rules` se validan contra `config/cv_variants.yaml`, no contra
`policy` del propio banco.** `policy.allowed_contribution_verbs`/
`blocked_ownership_verbs` no los lee ningún código hoy -ni `claim_rules.py`
ni `build.py`-, solo el `claim_rules.professional_contribution_language`
de `cv_variants.yaml`; ese fichero no se edita en M2 (es M3), así que se
lee de solo lectura del mismo clon ya sincronizado. Se valida **todo**
bullet cuyo `(evidence_status, cv_usage)` final sea
`(verified, eligible_with_internal_policy_check)` -no solo los que hoy
estén en el `candidate_bullet_priority` de alguna variante, a diferencia
de `cv_builder.build.resolve_variant`-, porque revalidar el documento
entero es la misma disciplina que ya aplican los tres ficheros anteriores.
"""

from __future__ import annotations

import difflib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import FoldedScalarString

from futuro_api.data_repo_write import claim_language
from futuro_api.data_repo_write.models import (
    Bullet,
    BulletBank,
    BulletEdit,
    ClaimRulesForValidation,
    EditableBulletBank,
)
from futuro_api.data_repo_write.vocabularies import BulletCvUsage, BulletEvidenceStatus
from futuro_api.data_repo_write.yaml_style import data_repo_yaml, set_folded_if_changed

RELATIVE_PATH = "cv/content/professional_bullet_bank.yaml"
CV_VARIANTS_RELATIVE_PATH = "config/cv_variants.yaml"


class BulletBankValidationError(Exception):
    """Los campos editados no cumplen el modelo, o violan las
    `claim_rules`. Nada se ha escrito."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return data_repo_yaml().load(text), text


def current(root: Path) -> BulletBank:
    doc, _ = _load(root)
    return BulletBank.model_validate(dict(doc))


def _load_claim_rules(root: Path) -> ClaimRulesForValidation:
    """Lee `config/cv_variants.yaml` de solo lectura. No se edita en M2."""
    text = (root / CV_VARIANTS_RELATIVE_PATH).read_text()
    doc = data_repo_yaml().load(text)
    return ClaimRulesForValidation.model_validate(doc["claim_rules"])


def _new_bullet_row(edit: BulletEdit) -> CommentedMap:
    # Sin proyecto ni confirmación de confidencialidad todavía: no se
    # fabrica una autorización que nadie ha dado. `bullet_type: role_scope`
    # es el único valor real del fichero que ya viene con `project_id: null`.
    return CommentedMap(
        [
            ("bullet_id", edit.bullet_id),
            ("bullet_type", "role_scope"),
            ("project_id", None),
            ("angle", edit.bullet_id),
            ("text_en", FoldedScalarString(edit.text_en)),
            ("evidence_status", edit.evidence_status.value),
            ("confidentiality_status", None),
            ("cv_usage", edit.cv_usage.value),
            ("role_variants", CommentedSeq()),
            ("blocked_by", CommentedSeq()),
        ]
    )


def _set_scalar_if_changed(mapping: Any, key: str, value: str) -> None:
    if str(mapping[key]) != value:
        mapping[key] = value


def _apply(doc: Any, edit: EditableBulletBank, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at
    bullets = doc["bullets"]
    by_id = {str(item["bullet_id"]): item for item in bullets}
    for row in edit.bullets:
        item = by_id.get(row.bullet_id)
        if item is not None:
            set_folded_if_changed(item, "text_en", row.text_en)
            _set_scalar_if_changed(item, "evidence_status", row.evidence_status.value)
            _set_scalar_if_changed(item, "cv_usage", row.cv_usage.value)
        else:
            bullets.append(_new_bullet_row(row))
    # Sin borrar: un `bullet_id` que el envío no traiga se queda como
    # estaba -mismo criterio que `disqualifying_conditions` en M1-.


def _validate_claim_rules(root: Path, bullets: tuple[Bullet, ...]) -> None:
    claim_rules = _load_claim_rules(root)
    for bullet in bullets:
        if (
            bullet.evidence_status == BulletEvidenceStatus.VERIFIED
            and bullet.cv_usage == BulletCvUsage.ELIGIBLE_WITH_INTERNAL_POLICY_CHECK
        ):
            try:
                claim_language.validate_contribution_language(
                    bullet.bullet_id, bullet.text_en, claim_rules
                )
            except claim_language.ClaimRuleViolation as error:
                raise BulletBankValidationError(str(error)) from error


@dataclass(frozen=True)
class BulletBankDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: BulletBank


def prepare(root: Path, edit: EditableBulletBank, *, today: date) -> BulletBankDiff:
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = BulletBank.model_validate(dict(doc))
    except ValidationError as error:
        raise BulletBankValidationError(str(error)) from error

    _validate_claim_rules(root, validated.bullets)

    buf = io.StringIO()
    data_repo_yaml().dump(doc, buf)
    new_text = buf.getvalue()

    diff = "".join(
        difflib.unified_diff(
            original_text.splitlines(True),
            new_text.splitlines(True),
            fromfile=RELATIVE_PATH,
            tofile=RELATIVE_PATH,
        )
    )
    return BulletBankDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(root: Path, edit: EditableBulletBank, *, today: date) -> BulletBankDiff:
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
