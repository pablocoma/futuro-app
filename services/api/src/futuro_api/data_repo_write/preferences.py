"""`config/preferences.yaml`, Fase 2 M1.

Mismo mecanismo que `objectives.py`: es lo único que sabe que este fichero
existe y qué forma tiene. Ninguna de sus nueve claves es vocabulario de
código -confirmado por grep antes de escribir este módulo-, así que no hay
ninguna puerta de enum que abrir aquí, a diferencia de `role_families` en
`objectives.py`.

Todos los campos de texto largo (`condition`, `savings_baseline_note`,
`abroad_housing_assumption`, `outside_madrid_rule`, `cv_policy`,
`acceptable_evidence`, `cv_implication`) son bloque plegado en el fichero
real, y se escriben de vuelta con `set_folded_if_changed` -nunca una
reasignación directa- para no reflowar una línea que el formulario no tocó.
"""

from __future__ import annotations

import difflib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from futuro_api.data_repo_write.models import EditablePreferences, Preferences
from futuro_api.data_repo_write.yaml_style import (
    data_repo_yaml,
    set_folded_if_changed,
    set_string_list_if_changed,
)

RELATIVE_PATH = "config/preferences.yaml"


class PreferencesValidationError(Exception):
    """Los campos editados no cumplen el modelo. Nada se ha escrito."""

    def __init__(self, error: ValidationError) -> None:
        super().__init__(str(error))
        self.errors = error.errors()


@dataclass(frozen=True)
class PreferencesDiff:
    original_text: str
    new_text: str
    unified_diff: str
    validated: Preferences


def _load(root: Path) -> tuple[Any, str]:
    text = (root / RELATIVE_PATH).read_text()
    return data_repo_yaml().load(text), text


def current(root: Path) -> Preferences:
    doc, _ = _load(root)
    return Preferences.model_validate(dict(doc))


def _apply(doc: Any, edit: EditablePreferences, *, updated_at: date) -> None:
    doc["updated_at"] = updated_at

    wc = doc["work_content"]
    wc["preference"] = edit.work_content.preference
    wc["avoid_narrow_specialization"] = edit.work_content.avoid_narrow_specialization
    wc["client_facing"] = edit.work_content.client_facing
    wc["programming"] = edit.work_content.programming
    wc["travel"] = edit.work_content.travel

    wi = doc["work_intensity"]
    wi["willing_to_accept_high_intensity"] = (
        edit.work_intensity.willing_to_accept_high_intensity
    )
    # Mutar en su sitio y no reemplazar: conserva el `[2, 4]` en flujo, como
    # `expected_tenure_years` en `objectives.py`.
    duration = wi["intended_duration_years"]
    duration[0], duration[1] = edit.work_intensity.intended_duration_years
    set_folded_if_changed(wi, "condition", edit.work_intensity.condition)

    wm = doc["work_mode"]
    wm["onsite"] = edit.work_mode.onsite
    wm["hybrid"] = edit.work_mode.hybrid
    wm["remote"] = edit.work_mode.remote

    geo = doc["geography"]
    geo["eu_passport"] = edit.geography.eu_passport
    geo["visa_sponsorship"] = edit.geography.visa_sponsorship
    geo["countries"] = edit.geography.countries
    geo["madrid_advantage"] = edit.geography.madrid_advantage

    comp = doc["compensation"]
    comp["spain_minimum_gross_eur"] = edit.compensation.spain_minimum_gross_eur
    comp["current_madrid_gross_eur"] = edit.compensation.current_madrid_gross_eur
    comp["current_madrid_net_monthly_eur"] = (
        edit.compensation.current_madrid_net_monthly_eur
    )
    comp["current_madrid_payments_per_year"] = (
        edit.compensation.current_madrid_payments_per_year
    )
    living_costs = comp["current_living_costs_monthly_eur"]
    living_costs[0], living_costs[1] = (
        edit.compensation.current_living_costs_monthly_eur
    )
    comp["current_annual_savings_eur"] = edit.compensation.current_annual_savings_eur
    set_folded_if_changed(
        comp, "savings_baseline_note", edit.compensation.savings_baseline_note
    )
    set_folded_if_changed(
        comp, "abroad_housing_assumption", edit.compensation.abroad_housing_assumption
    )
    set_folded_if_changed(
        comp, "outside_madrid_rule", edit.compensation.outside_madrid_rule
    )
    comp["international_targets"] = edit.compensation.international_targets

    lang = doc["language"]
    lang["spanish"] = edit.language.spanish
    lang["english_interview"] = edit.language.english_interview
    set_string_list_if_changed(lang, "evidence", edit.language.evidence)
    set_folded_if_changed(lang, "cv_policy", edit.language.cv_policy)

    ppd = doc["professional_project_documentation"]
    documentation = edit.professional_project_documentation
    ppd["contribution_granularity"] = documentation.contribution_granularity
    ppd["avoid_internal_task_breakdown"] = documentation.avoid_internal_task_breakdown
    set_folded_if_changed(ppd, "acceptable_evidence", documentation.acceptable_evidence)
    set_folded_if_changed(ppd, "cv_implication", documentation.cv_implication)


def prepare(root: Path, edit: EditablePreferences, *, today: date) -> PreferencesDiff:
    doc, original_text = _load(root)
    _apply(doc, edit, updated_at=today)

    try:
        validated = Preferences.model_validate(dict(doc))
    except ValidationError as error:
        raise PreferencesValidationError(error) from error

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
    return PreferencesDiff(
        original_text=original_text,
        new_text=new_text,
        unified_diff=diff,
        validated=validated,
    )


def write(root: Path, edit: EditablePreferences, *, today: date) -> PreferencesDiff:
    result = prepare(root, edit, today=today)
    (root / RELATIVE_PATH).write_text(result.new_text)
    return result
