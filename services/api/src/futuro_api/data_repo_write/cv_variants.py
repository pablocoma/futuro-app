"""`config/cv_variants.yaml`, Fase 2 M3.

Mismo mecanismo que los cuatro módulos anteriores. Lo propio de este:

**`claim_rules`, `fixed_sections`, `tailorable_sections`,
`vacancy_tailoring_process` y `strategy` son de solo lectura, sin ningún
camino de edición.** `fixed_sections` por regla dura de `AGENTS.md`;
`claim_rules` porque M2 ya depende de él como barrera externa que valida
cada bullet al guardarlo -decidido con Pablo el 2026-09-07 no ofrecerle
aquí el mismo criterio permisivo que sí se le dio a `hard_constraints` en
M1-. Se leen y se reescriben tal cual, mismo tratamiento que `policy` en
`BulletBank`.

**`base_variants` tiene 6 claves reales, solo 5 son editables.**
`quant_exploratory` -detectada por traer `status`, no por su nombre- no
tiene las listas de prioridad y no tiene contraparte en
`role_variant_content.yaml`: decidido con Pablo el 2026-09-07, queda de
solo lectura y fuera de la validación cruzada. Las 5 activas comparten un
núcleo editable (`target_roles`/`emphasis`/`professional_project_priority`/
`public_project_priority`/`candidate_bullet_priority`); sus campos
atípicos (`display_name`, `target_role_condition`, `note`,
`exclusive_evidence`) son de solo lectura, mismo patrón que los campos no
gestionados de `Bullet`.

**Validación cruzada, de solo lectura contra los otros dos ficheros ya
sincronizados en el mismo clon** -sin clon nuevo-: cada `bullet_id` en
`candidate_bullet_priority`/`exclusive_evidence` debe existir en
`professional_bullet_bank.yaml` (`exclusive_evidence` se revalida aunque
no se edite aquí, misma disciplina de "revalidar el documento entero" que
ya aplican los cuatro módulos anteriores); cada `project_id` en
`professional_project_priority`/`public_project_priority` debe existir en
`profile/project_catalog.yaml`; y las claves de
`role_variant_content.yaml` deben ser subconjunto de las variantes
activas -inclusión, no igualdad: `quant_exploratory` puede quedar sin
contraparte-.
"""

from __future__ import annotations

import difflib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from futuro_api.data_repo_write import (
    bullet_bank,
    project_catalog,
    role_variant_content,
)
from futuro_api.data_repo_write.models import (
    CvVariants,
    EditableCvVariants,
)
from futuro_api.data_repo_write.yaml_style import (
    data_repo_yaml,
    set_string_list_if_changed,
)

RELATIVE_PATH = "config/cv_variants.yaml"


class CvVariantsValidationError(Exception):
    """Los campos editados no cumplen el modelo, o alguna referencia
    cruzada no existe. Nada se ha escrito."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return data_repo_yaml().load(text), text


def current(root: Path) -> CvVariants:
    doc, _ = _load(root)
    return CvVariants.model_validate(dict(doc))


def _active_variant_ids(variants: Any) -> set[str]:
    return {key for key, row in variants.items() if "status" not in row}


def _apply(doc: Any, edit: EditableCvVariants, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at
    variants = doc["base_variants"]
    active = _active_variant_ids(variants)
    edited = set(edit.base_variants.keys())
    if active != edited:
        missing = sorted(active - edited)
        extra = sorted(edited - active)
        problems = []
        if missing:
            problems.append(f"faltan {missing}")
        if extra:
            problems.append(f"sobran {extra}")
        raise CvVariantsValidationError(
            "base_variants no coincide con las variantes activas "
            f"({', '.join(problems)}); las variantes con status son de "
            "solo lectura y esta rebanada no da de alta ni de baja variantes"
        )

    for key, edit_row in edit.base_variants.items():
        variant_doc = variants[key]
        set_string_list_if_changed(variant_doc, "target_roles", edit_row.target_roles)
        set_string_list_if_changed(variant_doc, "emphasis", edit_row.emphasis)
        set_string_list_if_changed(
            variant_doc,
            "professional_project_priority",
            edit_row.professional_project_priority,
        )
        set_string_list_if_changed(
            variant_doc, "public_project_priority", edit_row.public_project_priority
        )
        set_string_list_if_changed(
            variant_doc,
            "candidate_bullet_priority",
            edit_row.candidate_bullet_priority,
        )


def _validate_cross_references(root: Path, validated: CvVariants) -> None:
    known_bullet_ids = {b.bullet_id for b in bullet_bank.current(root).bullets}
    known_project_ids = project_catalog.current(root).project_id_set
    content_keys = set(role_variant_content.current(root).variants)

    problems: list[str] = []

    missing_bullets = sorted(validated.referenced_bullet_ids - known_bullet_ids)
    if missing_bullets:
        problems.append(
            "candidate_bullet_priority/exclusive_evidence referencia un "
            f"bullet_id que no existe en professional_bullet_bank.yaml: "
            f"{missing_bullets}"
        )

    missing_projects = sorted(validated.referenced_project_ids - known_project_ids)
    if missing_projects:
        problems.append(
            "professional_project_priority/public_project_priority "
            f"referencia un project_id que no existe en "
            f"project_catalog.yaml: {missing_projects}"
        )

    orphaned_content = sorted(content_keys - validated.active_variant_ids)
    if orphaned_content:
        problems.append(
            "role_variant_content.yaml declara variantes sin base_variants "
            f"activo correspondiente: {orphaned_content}"
        )

    if problems:
        raise CvVariantsValidationError("; ".join(problems))


@dataclass(frozen=True)
class CvVariantsDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: CvVariants


def prepare(root: Path, edit: EditableCvVariants, *, today: date) -> CvVariantsDiff:
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = CvVariants.model_validate(dict(doc))
    except ValidationError as error:
        raise CvVariantsValidationError(str(error)) from error

    _validate_cross_references(root, validated)

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
    return CvVariantsDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(root: Path, edit: EditableCvVariants, *, today: date) -> CvVariantsDiff:
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
