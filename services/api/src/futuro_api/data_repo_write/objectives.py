"""`config/objectives.yaml`, el primer fichero editable de Fase 2.

Es lo único de este módulo que sabe que ese fichero existe, tiene esa
forma, y se edita así. El mecanismo genérico -clonar, `pull --rebase`,
commit, push, conflicto- vive en `git_ops.py` y no cambia una línea al
llegar M1-M4 con sus propios ficheros.

**El estilo del YAML no es gusto de esta app: es el del fichero real**, y
hay que igualarlo o cada edición ensuciaría el diff con un reformateo que
no viene a cuento. Comprobado byte a byte contra el repositorio privado
real el 2026-09-06 -ver `docs/decisions/fase-2-perfil-editable.md`-:
`sequence=4, offset=2` reproduce el guion de las listas alineado bajo su
clave, y el `[2, 4]` de `expected_tenure_years` solo sobrevive si se muta
la lista en su sitio en vez de reemplazarla -reemplazarla la convertiría en
bloque-. El párrafo de `primary_objective.statement` usa bloque plegado
(`>-`); se escribe de vuelta con `FoldedScalarString` para no perder ese
estilo y quedar como una cadena entrecomillada de una sola línea.
"""

from __future__ import annotations

import difflib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

from futuro_api.data_repo_write.models import EditableObjectives, Objectives

RELATIVE_PATH = "config/objectives.yaml"


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


class ObjectivesValidationError(Exception):
    """Los campos editados no cumplen el modelo. Nada se ha escrito."""

    def __init__(self, error: ValidationError) -> None:
        super().__init__(str(error))
        self.errors = error.errors()


@dataclass(frozen=True)
class ObjectivesDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: Objectives


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return _yaml().load(text), text


def current(root: Path) -> Objectives:
    """Lo que hay hoy en el fichero, para rellenar el formulario."""
    doc, _ = _load(root)
    return Objectives.model_validate(dict(doc))


def _apply(doc: Any, edit: EditableObjectives, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at
    doc["transition"]["target_year"] = edit.transition.target_year
    doc["transition"]["urgency"] = edit.transition.urgency
    # Mutar en su sitio y no reemplazar: es lo que conserva el `[2, 4]` en
    # flujo en vez de convertirlo en una lista de bloque.
    tenure = doc["transition"]["expected_tenure_years"]
    tenure[0], tenure[1] = edit.transition.expected_tenure_years
    doc["primary_objective"]["statement"] = FoldedScalarString(
        edit.primary_objective.statement
    )
    doc["success_dimensions"] = list(edit.success_dimensions)
    doc["role_families"]["core"] = list(edit.role_families.core)
    doc["role_families"]["exploratory"] = list(edit.role_families.exploratory)


def prepare(root: Path, edit: EditableObjectives, *, today: date) -> ObjectivesDiff:
    """Aplica `edit` sobre una copia del documento y calcula su diff.

    No escribe nada: `root` se lee, nunca se toca desde aquí. Quien llama
    decide cuándo este cálculo se convierte en commit -y lo repite con un
    `pull --rebase` fresco delante en vez de fiarse de un resultado que
    pudo quedar viejo mientras alguien miraba la pantalla-.
    """
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = Objectives.model_validate(dict(doc))
    except ValidationError as error:
        raise ObjectivesValidationError(error) from error

    buf = io.StringIO()
    _yaml().dump(doc, buf)
    new_text = buf.getvalue()

    diff = "".join(
        difflib.unified_diff(
            original_text.splitlines(True),
            new_text.splitlines(True),
            fromfile=RELATIVE_PATH,
            tofile=RELATIVE_PATH,
        )
    )
    return ObjectivesDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(root: Path, edit: EditableObjectives, *, today: date) -> ObjectivesDiff:
    """Igual que `prepare`, y además escribe el resultado en `root`.

    Separado de `git_ops.commit_and_push` a propósito: escribir en disco es
    parte de "qué es `objectives.yaml`"; commitear y empujar es parte del
    mecanismo genérico, que no sabe de ficheros concretos.
    """
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
