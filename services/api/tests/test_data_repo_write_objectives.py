"""`objectives.py`: aplicar una edición, validarla, calcular el diff, y
solo escribir cuando se pide. Nada de git aquí -eso ya lo prueba
`test_data_repo_write_git_ops.py`-, solo el fichero.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from futuro_api.data_repo_write import objectives
from futuro_api.data_repo_write.models import (
    EditableObjectives,
    PrimaryObjective,
    RoleFamilies,
    Transition,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _edit(**overrides: object) -> EditableObjectives:
    base = dict(
        transition=Transition(
            target_year=2030, urgency="low", expected_tenure_years=(2, 4)
        ),
        primary_objective=PrimaryObjective(statement="Un objetivo cualquiera."),
        success_dimensions=("net_savings", "transferable_learning"),
        role_families=RoleFamilies(core=("data_engineer",), exploratory=()),
    )
    base.update(overrides)
    return EditableObjectives.model_validate(base)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = objectives.current(root)
    assert current.version == 1
    assert current.updated_at == date(2026, 1, 1)
    assert current.role_families.core == ("data_engineer", "data_scientist")


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / objectives.RELATIVE_PATH).read_bytes()
    result = objectives.prepare(root, _edit(), today=date(2026, 9, 6))

    assert (root / objectives.RELATIVE_PATH).read_bytes() == original
    assert "urgency: low" in result.new_text
    assert result.validated.updated_at == date(2026, 9, 6)
    assert "-updated_at: 2026-01-01" in result.unified_diff
    assert "+updated_at: 2026-09-06" in result.unified_diff


def test_prepare_conserva_el_comentario_de_cabecera(root: Path) -> None:
    result = objectives.prepare(root, _edit(), today=date(2026, 9, 6))
    assert result.new_text.startswith("# Objetivos INVENTADOS")


def test_prepare_conserva_el_estilo_de_las_listas_de_flujo(root: Path) -> None:
    result = objectives.prepare(
        root,
        _edit(
            transition=Transition(
                target_year=2030, urgency="low", expected_tenure_years=(3, 5)
            )
        ),
        today=date(2026, 9, 6),
    )
    assert "expected_tenure_years: [3, 5]" in result.new_text


def test_role_families_rechaza_una_familia_que_el_codigo_no_conoce() -> None:
    """La puerta de verdad está en el modelo: ni siquiera llega a
    `prepare` -y por tanto tampoco al endpoint- un valor que
    `RoleFamily` no reconozca."""
    with pytest.raises(ValueError, match="no reconoce"):
        RoleFamilies(core=("inventada",), exploratory=())


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    """`version` no está en el formulario, pero sigue siendo parte del
    fichero: si quedó corrupta por algo ajeno a esta app -una edición a
    mano, un merge raro-, `prepare` tiene que notarlo igual, porque valida
    el documento completo tras aplicar la edición y no solo los campos que
    el formulario tocó."""
    path = root / objectives.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 1", "version: 0"))

    with pytest.raises(objectives.ObjectivesValidationError):
        objectives.prepare(root, _edit(), today=date(2026, 9, 6))

    # Nada se ha escrito de más: la validación es anterior a cualquier
    # escritura, y lo único en disco sigue siendo la corrupción de arriba.
    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(
        primary_objective=PrimaryObjective(statement="Objetivo distinto de verdad.")
    )
    objectives.write(root, edit, today=date(2026, 9, 6))

    reread = objectives.current(root)
    assert reread.primary_objective.statement == "Objetivo distinto de verdad."
    assert reread.updated_at == date(2026, 9, 6)
    # `version` no lo toca el formulario: se queda como estaba.
    assert reread.version == 1
