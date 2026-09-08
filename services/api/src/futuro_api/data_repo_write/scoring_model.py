"""`config/scoring_model.yaml`, Fase 2 M4 -- la última rebanada de Fase 2.

Mismo mecanismo que los cinco módulos anteriores: `current`/`prepare`/
`write`, revalida el documento entero tras aplicar la edición. Sin
validación cruzada con otros ficheros -a diferencia de M3, ninguna
referencia de este fichero a otro es un identificador que el código
resuelva-.

Lo propio de este módulo:

**`weights`/`anchors` viven como dos mapas paralelos en el YAML, y se
editan como una sola lista de `DimensionEdit`** -nombre, peso, filas de
ancla-. `_apply_dimensions` reconstruye los dos mapas a la vez: alta,
baja y renombrado de dimensión son libres -ver `models.py` para el
porqué-, y cada fila de ancla se casa por su etiqueta (`"0"`, `"assumption"`,
...) dentro de la dimensión, nunca por posición.

**`gates` se edita con el mismo criterio**, una fila por filtro con sus
propias etiquetas (`pass`/`fail`/`context`/...).

**Solo `output.effort_tier.evaluation_order` se toca dentro de
`output`.** El resto del bloque -`required_fields`, y `when`/`do`/`note`
de cada nivel- es documentación de umbrales que en realidad decide a
mano `assessment/scoring.py`, así que nunca se reconstruye: se deja
intacto por construcción, sin ningún camino de escritura hacia él.

**Hallazgo de este módulo, no visto en M0-M3**: reasignar un escalar
**numérico** sin comprobar antes si cambió pierde formato -no solo pasa
con texto plegado o secuencias-. Ver `yaml_style.set_scalar_if_changed`
y su docstring para el porqué; se usa aquí para el peso de una
dimensión, los campos de `baseline`, `minimum_coverage` y
`portfolio_policy`.
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
    DimensionEdit,
    EditableScoringModel,
    GateEdit,
    ScoringModel,
    is_anchor_level,
)
from futuro_api.data_repo_write.yaml_style import (
    data_repo_yaml,
    set_folded_if_changed,
    set_folded_list_if_changed,
    set_scalar_if_changed,
    set_string_list_if_changed,
)

RELATIVE_PATH = "config/scoring_model.yaml"


class ScoringModelValidationError(Exception):
    """Los campos editados no cumplen el modelo, o el fichero no tiene la
    forma esperada. Nada se ha escrito."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return data_repo_yaml().load(text), text


def _baseline_key(doc: Any) -> str:
    """El único nombre de bloque `baseline_*`, igual que exige
    `data_repo/loader.py` del lado de solo lectura."""
    keys = [str(key) for key in doc if str(key).startswith("baseline_")]
    if len(keys) != 1:
        raise ScoringModelValidationError(
            f"«{RELATIVE_PATH}»: se esperaba exactamente un bloque «baseline_*» "
            f"y hay {len(keys)}"
        )
    return keys[0]


def _anchor_key(label: str) -> int | str:
    return int(label) if is_anchor_level(label) else label


def _read_dimensions(doc: Any) -> list[dict[str, Any]]:
    weights = doc["weights"]
    anchors = doc["anchors"]
    dimensions = []
    for name, weight in weights.items():
        block = anchors.get(name) or {}
        rows = [{"label": str(label), "text": text} for label, text in block.items()]
        dimensions.append({"name": str(name), "weight": weight, "anchors": rows})
    return dimensions


def _read_gates(doc: Any) -> list[dict[str, Any]]:
    gates = doc["gates"]
    rows = []
    for name, body in gates.items():
        entries = [{"label": str(label), "text": text} for label, text in body.items()]
        rows.append({"name": str(name), "rows": entries})
    return rows


def _to_validation_dict(doc: Any) -> dict[str, Any]:
    baseline_key = _baseline_key(doc)
    missing_data = doc["missing_data"]
    effort_tier = doc["output"]["effort_tier"]

    return {
        "version": doc["version"],
        "status": doc["status"],
        "updated_at": doc["updated_at"],
        "description": doc["description"],
        "baseline_name": baseline_key,
        "baseline": doc[baseline_key],
        "dimensions": _read_dimensions(doc),
        "scale": doc["scale"],
        "gates": _read_gates(doc),
        "probability_bands": doc["probability_bands"],
        "portfolio_assignment": doc["portfolio_assignment"],
        "portfolio_policy": doc["portfolio_policy"],
        "minimum_coverage": float(missing_data["minimum_coverage"]),
        "never_rule": str(missing_data["never"]),
        "missing_data": missing_data,
        "effort_evaluation_order": list(effort_tier["evaluation_order"]),
        "output": doc["output"],
        "notes": list(doc.get("notes") or ()),
    }


def current(root: Path) -> ScoringModel:
    doc, _ = _load(root)
    return ScoringModel.model_validate(_to_validation_dict(doc))


def _apply_dimensions(doc: Any, edits: tuple[DimensionEdit, ...]) -> None:
    weights = doc["weights"]
    anchors = doc["anchors"]
    existing_names = set(weights.keys()) | set(anchors.keys())
    edited_names = {edit.name for edit in edits}

    for name in existing_names - edited_names:
        weights.pop(name, None)
        anchors.pop(name, None)

    for edit in edits:
        if edit.name in weights:
            set_scalar_if_changed(weights, edit.name, edit.weight)
        else:
            weights[edit.name] = edit.weight

        block = anchors.get(edit.name)
        if block is None:
            block = CommentedMap()
            anchors[edit.name] = block
        desired = {_anchor_key(row.label): row.text for row in edit.anchors}
        for key in set(block.keys()) - set(desired):
            del block[key]
        for key, text in desired.items():
            if key in block:
                set_folded_if_changed(block, key, text)
            else:
                block[key] = FoldedScalarString(text)


def _apply_gates(doc: Any, edits: tuple[GateEdit, ...]) -> None:
    gates = doc["gates"]
    existing_names = set(gates.keys())
    edited_names = {edit.name for edit in edits}

    for name in existing_names - edited_names:
        del gates[name]

    for edit in edits:
        body = gates.get(edit.name)
        if body is None:
            body = CommentedMap()
            gates[edit.name] = body
        desired = {row.label: row.text for row in edit.rows}
        for label in set(body.keys()) - set(desired):
            del body[label]
        for label, text in desired.items():
            if label in body:
                set_folded_if_changed(body, label, text)
            else:
                body[label] = FoldedScalarString(text)


def _apply(doc: Any, edit: EditableScoringModel, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at
    set_folded_if_changed(doc, "description", edit.description)

    baseline = doc[_baseline_key(doc)]
    b = edit.baseline
    # El propio `updated_at` de `baseline_*` es distinto del `updated_at`
    # del documento: el segundo se estampa siempre -"la app tocó este
    # fichero hoy"-, pero el primero dice "estos datos económicos se
    # verificaron por última vez este día", así que solo debe moverse si
    # de verdad cambió algún campo de la línea base, no en cualquier
    # escritura -por ejemplo, al editar solo un filtro-.
    baseline_changed = (
        baseline["gross_annual_eur"],
        baseline["payments_per_year"],
        baseline["net_monthly_eur"],
        baseline["net_annual_eur"],
        tuple(baseline["living_costs_monthly_eur"]),
        tuple(baseline["annual_savings_eur"]),
        baseline["reference_savings_eur"],
        baseline["savings_rate"],
        str(baseline["cause"]),
        str(baseline["implication"]),
    ) != (
        b.gross_annual_eur,
        b.payments_per_year,
        b.net_monthly_eur,
        b.net_annual_eur,
        b.living_costs_monthly_eur,
        b.annual_savings_eur,
        b.reference_savings_eur,
        b.savings_rate,
        b.cause,
        b.implication,
    )

    set_scalar_if_changed(baseline, "gross_annual_eur", b.gross_annual_eur)
    set_scalar_if_changed(baseline, "payments_per_year", b.payments_per_year)
    set_scalar_if_changed(baseline, "net_monthly_eur", b.net_monthly_eur)
    set_scalar_if_changed(baseline, "net_annual_eur", b.net_annual_eur)
    # Mutar en su sitio y no reemplazar: es lo que conserva el flujo `[a, b]`
    # en vez de convertirlo en una lista de bloque -mismo hallazgo de M0
    # sobre `expected_tenure_years`-.
    living_costs = baseline["living_costs_monthly_eur"]
    living_costs[0], living_costs[1] = b.living_costs_monthly_eur
    annual_savings = baseline["annual_savings_eur"]
    annual_savings[0], annual_savings[1] = b.annual_savings_eur
    set_scalar_if_changed(baseline, "reference_savings_eur", b.reference_savings_eur)
    set_scalar_if_changed(baseline, "savings_rate", b.savings_rate)
    set_folded_if_changed(baseline, "cause", b.cause)
    set_folded_if_changed(baseline, "implication", b.implication)
    if baseline_changed:
        # `.replace()` sin argumentos, no `updated_at` tal cual: este
        # fichero es el primero en estampar la misma fecha en dos sitios
        # (aquí y en `doc["updated_at"]`), y `ruamel` representa dos
        # valores que son el mismo objeto de Python como un ancla y un
        # alias YAML (`&id001`/`*id001`) en vez de repetir el escalar -
        # comprobado el 2026-09-08-, lo que además le hizo perder la línea
        # en blanco que separaba el bloque de `baseline_*` del siguiente.
        # Un objeto `date` distinto, aunque con el mismo valor, evita la
        # alias por completo.
        baseline["updated_at"] = updated_at.replace()

    _apply_dimensions(doc, edit.dimensions)
    _apply_gates(doc, edit.gates)

    pb = doc["probability_bands"]
    set_folded_if_changed(pb, "high", edit.probability_bands.high)
    set_folded_if_changed(pb, "medium", edit.probability_bands.medium)
    set_folded_if_changed(pb, "low", edit.probability_bands.low)
    set_folded_if_changed(pb, "very_low", edit.probability_bands.very_low)

    missing_data = doc["missing_data"]
    set_scalar_if_changed(missing_data, "minimum_coverage", edit.minimum_coverage)
    set_folded_if_changed(missing_data, "never", edit.never_rule)

    # `output.required_fields` y el resto de `output.effort_tier` -cada
    # nivel con su `when`/`do`, y `.note`- no se tocan nunca: solo
    # `evaluation_order` es un dato que de verdad recorre
    # `assessment/scoring.py`, ver `models.py` para el porqué.
    set_string_list_if_changed(
        doc["output"]["effort_tier"],
        "evaluation_order",
        [tier.value for tier in edit.effort_evaluation_order],
    )

    pp = doc["portfolio_policy"]
    set_scalar_if_changed(pp, "realistic", edit.portfolio_policy.realistic)
    set_scalar_if_changed(
        pp, "realistic_stretch", edit.portfolio_policy.realistic_stretch
    )
    set_scalar_if_changed(pp, "aspirational", edit.portfolio_policy.aspirational)
    set_scalar_if_changed(pp, "experimental", edit.portfolio_policy.experimental)
    set_scalar_if_changed(pp, "status", edit.portfolio_policy.status)
    set_folded_if_changed(pp, "note", edit.portfolio_policy.note)

    set_folded_list_if_changed(doc, "notes", edit.notes)


@dataclass(frozen=True)
class ScoringModelDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: ScoringModel


def prepare(root: Path, edit: EditableScoringModel, *, today: date) -> ScoringModelDiff:
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = ScoringModel.model_validate(_to_validation_dict(doc))
    except ValidationError as error:
        raise ScoringModelValidationError(str(error)) from error

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
    return ScoringModelDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(root: Path, edit: EditableScoringModel, *, today: date) -> ScoringModelDiff:
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
