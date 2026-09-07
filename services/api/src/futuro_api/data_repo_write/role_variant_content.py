"""`cv/content/role_variant_content.yaml`, Fase 2 M2.

Mismo mecanismo que los tres ficheros anteriores. Lo propio de este:

**Las 5 claves de `variants` son fijas.** Coinciden con `base_variants` de
`config/cv_variants.yaml` -M3, no se edita aquí-; añadir o quitar una
variante en este fichero la dejaría huérfana hasta que M3 exista.
Decidido con Pablo el 2026-09-07: el envío tiene que declarar exactamente
las claves que el fichero ya tiene, ni más ni menos. La comprobación vive
aquí y no en el modelo, porque el modelo no conoce el fichero vigente.

**`skills` es una lista de pares `{label, value}`, con CRUD completo.**
Sin identificador estable que casar -a diferencia de `bullets`-, así que
se casa por posición: la fila `i` existente se muta en su sitio si cambia
de contenido, las filas de más se añaden al final y las que sobran se
quitan del final. Nunca se reemplaza la `CommentedSeq` entera de una
tacada -comprobado con `role_variant_content.yaml` real: hacerlo, incluso
con contenido casi idéntico, perdía la línea en blanco que separaba una
variante de la siguiente, el mismo hallazgo que `yaml_style.py` documenta
para listas de nivel superior-.
"""

from __future__ import annotations

import difflib
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from ruamel.yaml.comments import CommentedMap

from futuro_api.data_repo_write.models import (
    EditableRoleVariantContent,
    RoleVariantContent,
    SkillRowEdit,
)
from futuro_api.data_repo_write.yaml_style import data_repo_yaml, set_folded_if_changed

RELATIVE_PATH = "cv/content/role_variant_content.yaml"


class RoleVariantContentValidationError(Exception):
    """Los campos editados no cumplen el modelo. Nada se ha escrito."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return data_repo_yaml().load(text), text


def current(root: Path) -> RoleVariantContent:
    doc, _ = _load(root)
    return RoleVariantContent.model_validate(dict(doc))


def _apply_skills(container: Any, key: str, rows: Iterable[SkillRowEdit]) -> None:
    """Muta `skills` en su sitio, fila a fila por posición.

    Editar o quitar filas existentes no ensucia el diff -se comprobó byte
    a byte contra el real-. **Añadir** una fila sí deja un rastro cosmético
    conocido y sin resolver: la línea en blanco que separaba esta variante
    de la siguiente queda antes de la fila nueva en vez de después, porque
    `ruamel` no traslada ese comentario de fin de bloque al añadir un
    elemento. El YAML resultante sigue siendo válido y el contenido
    correcto; es una línea en blanco mal colocada, no un dato perdido."""
    existing = container[key]
    new_rows = list(rows)
    for index, row in enumerate(new_rows):
        if index < len(existing):
            item = existing[index]
            if str(item["label"]) != row.label:
                item["label"] = row.label
            if str(item["value"]) != row.value:
                item["value"] = row.value
        else:
            existing.append(CommentedMap([("label", row.label), ("value", row.value)]))
    while len(existing) > len(new_rows):
        del existing[-1]


def _apply(doc: Any, edit: EditableRoleVariantContent, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at
    variants = doc["variants"]
    existing_keys = set(variants.keys())
    edited_keys = set(edit.variants.keys())
    if existing_keys != edited_keys:
        missing = sorted(existing_keys - edited_keys)
        extra = sorted(edited_keys - existing_keys)
        problems = []
        if missing:
            problems.append(f"faltan {missing}")
        if extra:
            problems.append(f"sobran {extra}")
        raise RoleVariantContentValidationError(
            "variants no coincide con las variantes declaradas "
            f"({', '.join(problems)}); esta rebanada no da de alta ni de "
            "baja variantes, solo edita su contenido"
        )

    for key, content in edit.variants.items():
        variant_doc = variants[key]
        if str(variant_doc["display_name"]) != content.display_name:
            variant_doc["display_name"] = content.display_name
        set_folded_if_changed(variant_doc, "use_when", content.use_when)
        set_folded_if_changed(variant_doc, "profile", content.profile)
        _apply_skills(variant_doc, "skills", content.skills)


@dataclass(frozen=True)
class RoleVariantContentDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: RoleVariantContent


def prepare(
    root: Path, edit: EditableRoleVariantContent, *, today: date
) -> RoleVariantContentDiff:
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = RoleVariantContent.model_validate(dict(doc))
    except ValidationError as error:
        raise RoleVariantContentValidationError(str(error)) from error

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
    return RoleVariantContentDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(
    root: Path, edit: EditableRoleVariantContent, *, today: date
) -> RoleVariantContentDiff:
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
