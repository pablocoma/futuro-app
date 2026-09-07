"""`config/constraints.yaml`, Fase 2 M1.

Mismo mecanismo que `objectives.py` y `preferences.py`. Dos claves tienen
una forma que ninguno de los dos ficheros anteriores tenía y que exigió su
propio experimento de ruamel antes de escribir código -ver
`docs/decisions/fase-2-perfil-editable.md`, sección de M1-:

**`disqualifying_conditions`** es una lista de diccionarios heterogéneos
-cada uno con `id` + `rule`, y además `evaluable_from_posting` *o*
`affects` según el caso-. El lado de solo lectura
(`data_repo/loader.py`) solo consume `id` y `rule`; el resto no es
vocabulario de código ni lo lee ningún sitio, así que el formulario no lo
toca y cada fila se casa por `id` para mutar su `rule` en su sitio sin
tocar los campos que no gestiona esta app. Alcance confirmado con Pablo el
2026-09-07: añadir filas y editar `rule`, sin borrar ni reordenar.

**`superseded_decisions`** es un mapa de clave -> texto, no una lista. El
formulario lo edita como CRUD completo -añadir, editar, borrar, decidido
con Pablo el 2026-09-07-, así que `_apply_superseded_decisions` borra las
claves que ya no estén, muta en su sitio las que cambien de texto, y añade
las nuevas al final, en vez de reconstruir el mapa entero -reconstruirlo
reflowaría el texto de toda entrada aunque no hubiera cambiado, el mismo
hallazgo que `set_folded_if_changed` corrige en los campos sueltos-.
"""

from __future__ import annotations

import difflib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import FoldedScalarString

from futuro_api.data_repo_write.models import (
    Constraints,
    DisqualifyingConditionEdit,
    EditableConstraints,
    SupersededDecisionEdit,
)
from futuro_api.data_repo_write.yaml_style import (
    data_repo_yaml,
    set_folded_if_changed,
    set_string_list_if_changed,
)

RELATIVE_PATH = "config/constraints.yaml"


class ConstraintsValidationError(Exception):
    """Los campos editados no cumplen el modelo. Nada se ha escrito."""

    def __init__(self, error: ValidationError) -> None:
        super().__init__(str(error))
        self.errors = error.errors()


@dataclass(frozen=True)
class ConstraintsDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: Constraints


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return data_repo_yaml().load(text), text


def current(root: Path) -> Constraints:
    doc, _ = _load(root)
    return Constraints.model_validate(dict(doc))


def _apply_disqualifying_conditions(
    doc: Any, edits: tuple[DisqualifyingConditionEdit, ...]
) -> None:
    conditions = doc["disqualifying_conditions"]
    by_id = {str(item["id"]): item for item in conditions}
    for edit in edits:
        item = by_id.get(edit.id)
        if item is not None:
            # Solo `rule`: el campo extra de cada fila (`evaluable_from_posting`
            # o `affects`, distinto según el caso) no lo gestiona el
            # formulario y se deja intacto.
            set_folded_if_changed(item, "rule", edit.rule)
        else:
            conditions.append(
                CommentedMap([("id", edit.id), ("rule", FoldedScalarString(edit.rule))])
            )
    # Sin borrar: un `id` que el formulario ya no traiga se queda como
    # estaba, porque esta rebanada no ofrece ningún camino para pedir su
    # borrado -confirmado con Pablo el 2026-09-07-.


def _apply_superseded_decisions(
    doc: Any, edits: tuple[SupersededDecisionEdit, ...]
) -> None:
    existing = doc["superseded_decisions"]
    keys_to_keep = {edit.key for edit in edits}
    for key in list(existing.keys()):
        if key not in keys_to_keep:
            del existing[key]
    for edit in edits:
        if edit.key in existing:
            set_folded_if_changed(existing, edit.key, edit.text)
        else:
            existing[edit.key] = FoldedScalarString(edit.text)


def _apply(doc: Any, edit: EditableConstraints, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at
    set_string_list_if_changed(doc, "hard_constraints", edit.hard_constraints)

    ckc = doc["current_known_constraints"]
    ckc["timing"] = edit.current_known_constraints.timing
    ckc["spain_salary_floor_gross_eur"] = (
        edit.current_known_constraints.spain_salary_floor_gross_eur
    )
    ckc["relocation"] = edit.current_known_constraints.relocation
    ckc["visa_sponsorship"] = edit.current_known_constraints.visa_sponsorship
    ckc["eu_work_authorization"] = edit.current_known_constraints.eu_work_authorization

    sp = doc["sector_policy"]
    set_string_list_if_changed(
        sp, "excluded_industries", edit.sector_policy.excluded_industries
    )
    set_folded_if_changed(sp, "rule", edit.sector_policy.rule)
    set_folded_if_changed(sp, "note", edit.sector_policy.note)

    _apply_disqualifying_conditions(doc, edit.disqualifying_conditions)

    ac = doc["accepted_conditions"]
    ac["on_call_and_shift_work"] = edit.accepted_conditions.on_call_and_shift_work
    set_folded_if_changed(ac, "high_intensity", edit.accepted_conditions.high_intensity)

    set_string_list_if_changed(doc, "pending_decisions", edit.pending_decisions)

    _apply_superseded_decisions(doc, edit.superseded_decisions)


def prepare(root: Path, edit: EditableConstraints, *, today: date) -> ConstraintsDiff:
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = Constraints.model_validate(dict(doc))
    except ValidationError as error:
        raise ConstraintsValidationError(error) from error

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
    return ConstraintsDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(root: Path, edit: EditableConstraints, *, today: date) -> ConstraintsDiff:
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
