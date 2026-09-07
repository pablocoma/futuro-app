"""`profile/project_catalog.yaml`, Fase 2 M3.

Primer módulo de escritura para este fichero -sin ningún camino de
lectura previo en la aplicación, confirmado por grep el 2026-09-07-.
Mismo mecanismo que los cuatro anteriores: `current`/`prepare`/`write`,
revalida el documento entero tras aplicar la edición.

**`project_id` casa cada edición, igual que `bullet_id` en M2. Sin alta ni
baja.** `discovery_backlog` -candidatos sin auditar- y la promoción de un
candidato a proyecto quedan fuera: es una decisión mayor con su propio
dossier y auditoría detrás, no algo que ofrezca un formulario.

**Editable por fila: `safe_name`, `evidence_status`, `cv_usage`,
`interview_usage`, `pending_confirmations`.** El resto de cada fila
-`source_type`, `confidentiality`, `canonical_source`, `role_family_fit`,
`professional_value_signals`- pasa intacto.
"""

from __future__ import annotations

import difflib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from futuro_api.data_repo_write.models import EditableProjectCatalog, ProjectCatalog
from futuro_api.data_repo_write.yaml_style import (
    data_repo_yaml,
    set_string_list_if_changed,
)

RELATIVE_PATH = "profile/project_catalog.yaml"


class ProjectCatalogValidationError(Exception):
    """Los campos editados no cumplen el modelo. Nada se ha escrito."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return data_repo_yaml().load(text), text


def current(root: Path) -> ProjectCatalog:
    doc, _ = _load(root)
    return ProjectCatalog.model_validate(dict(doc))


def _set_scalar_if_changed(mapping: Any, key: str, value: str) -> None:
    if str(mapping[key]) != value:
        mapping[key] = value


def _apply(doc: Any, edit: EditableProjectCatalog, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at
    projects = doc["projects"]
    by_id = {str(item["project_id"]): item for item in projects}
    existing_ids = set(by_id)
    edited_ids = {row.project_id for row in edit.projects}
    if existing_ids != edited_ids:
        missing = sorted(existing_ids - edited_ids)
        extra = sorted(edited_ids - existing_ids)
        problems = []
        if missing:
            problems.append(f"faltan {missing}")
        if extra:
            problems.append(f"sobran {extra}")
        raise ProjectCatalogValidationError(
            "projects no coincide con los proyectos declarados "
            f"({', '.join(problems)}); esta rebanada no da de alta ni de "
            "baja proyectos, solo edita los que ya hay"
        )

    for row in edit.projects:
        item = by_id[row.project_id]
        _set_scalar_if_changed(item, "safe_name", row.safe_name)
        _set_scalar_if_changed(item, "evidence_status", row.evidence_status.value)
        _set_scalar_if_changed(item, "cv_usage", row.cv_usage.value)
        _set_scalar_if_changed(item, "interview_usage", row.interview_usage.value)
        set_string_list_if_changed(
            item, "pending_confirmations", row.pending_confirmations
        )


@dataclass(frozen=True)
class ProjectCatalogDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: ProjectCatalog


def prepare(
    root: Path, edit: EditableProjectCatalog, *, today: date
) -> ProjectCatalogDiff:
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = ProjectCatalog.model_validate(dict(doc))
    except ValidationError as error:
        raise ProjectCatalogValidationError(str(error)) from error

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
    return ProjectCatalogDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(
    root: Path, edit: EditableProjectCatalog, *, today: date
) -> ProjectCatalogDiff:
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
