"""`preferences.py`: aplicar una edición, validarla, calcular el diff, y
solo escribir cuando se pide. Nada de git aquí -eso ya lo prueba
`test_data_repo_write_git_ops.py`-, solo el fichero.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from futuro_api.data_repo_write import preferences
from futuro_api.data_repo_write.models import (
    Compensation,
    EditablePreferences,
    Geography,
    Language,
    ProfessionalProjectDocumentation,
    WorkContent,
    WorkIntensity,
    WorkMode,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _edit(**overrides: object) -> EditablePreferences:
    base: dict[str, object] = dict(
        work_content=WorkContent(
            preference="broad_and_varied",
            avoid_narrow_specialization=True,
            client_facing="acceptable",
            programming="acceptable",
            travel="acceptable",
        ),
        work_intensity=WorkIntensity(
            willing_to_accept_high_intensity=True,
            intended_duration_years=(2, 4),
            condition="La intensidad debe compensarse con ahorro, marca o "
            "aprendizaje excepcional. Texto inventado para el fixture.",
        ),
        work_mode=WorkMode(onsite="accepted", hybrid="accepted", remote="accepted"),
        geography=Geography(
            eu_passport=True,
            visa_sponsorship="accepted",
            countries="pending_research",
            madrid_advantage="no_rent",
        ),
        compensation=Compensation(
            spain_minimum_gross_eur=30000,
            current_madrid_gross_eur=24000,
            current_madrid_net_monthly_eur=1500,
            current_madrid_payments_per_year=12,
            current_living_costs_monthly_eur=(300, 400),
            current_annual_savings_eur=12000,
            savings_baseline_note="Cifra y explicación inventadas para el "
            "fixture, no un dato real.",
            abroad_housing_assumption="Alquilaría barato si se mudara: "
            "supuesto inventado para el fixture.",
            outside_madrid_rule="Debe superar el coste incremental de "
            "mudarse: regla inventada.",
            international_targets="pending_cost_of_living_analysis",
        ),
        language=Language(
            spanish="native",
            english_interview="functional",
            evidence=("invented_evidence_entry",),
            cv_policy="Política inventada para el fixture, no un dato real.",
        ),
        professional_project_documentation=ProfessionalProjectDocumentation(
            contribution_granularity="aggregate",
            avoid_internal_task_breakdown=True,
            acceptable_evidence="Descripción inventada de evidencia "
            "aceptable para el fixture.",
            cv_implication="Implicación inventada para el CV, dato de prueba.",
        ),
    )
    base.update(overrides)
    return EditablePreferences.model_validate(base)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = preferences.current(root)
    assert current.version == 1
    assert current.updated_at == date(2026, 1, 1)
    assert current.compensation.current_living_costs_monthly_eur == (300, 400)


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / preferences.RELATIVE_PATH).read_bytes()
    result = preferences.prepare(root, _edit(), today=date(2026, 9, 7))

    assert (root / preferences.RELATIVE_PATH).read_bytes() == original
    assert result.validated.updated_at == date(2026, 9, 7)
    assert "-updated_at: 2026-01-01" in result.unified_diff
    assert "+updated_at: 2026-09-07" in result.unified_diff


def test_prepare_conserva_el_estilo_de_las_listas_de_flujo(root: Path) -> None:
    result = preferences.prepare(
        root,
        _edit(
            work_intensity=WorkIntensity(
                willing_to_accept_high_intensity=True,
                intended_duration_years=(3, 5),
                condition="La intensidad debe compensarse con ahorro, marca "
                "o aprendizaje excepcional. Texto inventado para el fixture.",
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "intended_duration_years: [3, 5]" in result.new_text


def test_prepare_no_reflowa_un_campo_plegado_que_no_cambio(root: Path) -> None:
    """Mismo hallazgo que en `objectives.py`: editar un campo distinto y
    dejar un bloque plegado intacto no debe reflowar su línea."""
    current = preferences.current(root)
    result = preferences.prepare(
        root,
        _edit(
            compensation=Compensation(
                spain_minimum_gross_eur=31000,
                current_madrid_gross_eur=24000,
                current_madrid_net_monthly_eur=1500,
                current_madrid_payments_per_year=12,
                current_living_costs_monthly_eur=(300, 400),
                current_annual_savings_eur=12000,
                savings_baseline_note=current.compensation.savings_baseline_note,
                abroad_housing_assumption=current.compensation.abroad_housing_assumption,
                outside_madrid_rule=current.compensation.outside_madrid_rule,
                international_targets="pending_cost_of_living_analysis",
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "savings_baseline_note" not in result.unified_diff
    assert "abroad_housing_assumption" not in result.unified_diff
    assert "outside_madrid_rule" not in result.unified_diff
    assert "spain_minimum_gross_eur: 31000" in result.new_text


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    path = root / preferences.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 1", "version: 0"))

    with pytest.raises(preferences.PreferencesValidationError):
        preferences.prepare(root, _edit(), today=date(2026, 9, 7))

    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(
        geography=Geography(
            eu_passport=True,
            visa_sponsorship="accepted",
            countries="germany_and_netherlands",
            madrid_advantage="no_rent",
        )
    )
    preferences.write(root, edit, today=date(2026, 9, 7))

    reread = preferences.current(root)
    assert reread.geography.countries == "germany_and_netherlands"
    assert reread.updated_at == date(2026, 9, 7)
    assert reread.version == 1
