"""`constraints.py`: aplicar una edición, validarla, calcular el diff, y
solo escribir cuando se pide. Nada de git aquí -eso ya lo prueba
`test_data_repo_write_git_ops.py`-, solo el fichero.

Dos claves tienen forma propia y tests dedicados: `disqualifying_conditions`
(lista de dicts heterogéneos, casada por `id`) y `superseded_decisions`
(mapa de clave -> texto, editado como CRUD).
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from futuro_api.data_repo_write import constraints
from futuro_api.data_repo_write.models import (
    AcceptedConditions,
    CurrentKnownConstraints,
    DisqualifyingConditionEdit,
    EditableConstraints,
    SectorPolicy,
    SupersededDecisionEdit,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _edit(**overrides: object) -> EditableConstraints:
    base = dict(
        hard_constraints=(
            "no_fabricated_claims",
            "no_employer_or_client_confidential_information",
        ),
        current_known_constraints=CurrentKnownConstraints(
            timing="transition_during_2026",
            spain_salary_floor_gross_eur=30000,
            relocation="accepted",
            visa_sponsorship="accepted",
            eu_work_authorization=True,
        ),
        sector_policy=SectorPolicy(
            excluded_industries=(),
            rule="Regla inventada de política sectorial para el fixture.",
            note="Nota inventada, no un dato real.",
        ),
        disqualifying_conditions=(
            DisqualifyingConditionEdit(
                id="invented_condition_one",
                rule="Regla inventada de descalificación número uno, para el fixture.",
            ),
            DisqualifyingConditionEdit(
                id="invented_condition_two",
                rule="Regla inventada de descalificación número dos, para el fixture.",
            ),
        ),
        accepted_conditions=AcceptedConditions(
            on_call_and_shift_work="aceptado",
            high_intensity="Aceptado según preferences.yaml, nota "
            "inventada para el fixture.",
        ),
        pending_decisions=("invented_pending_decision",),
        superseded_decisions=(
            SupersededDecisionEdit(
                key="invented_superseded_decision",
                text="Texto inventado explicando por qué se sustituyó esta decisión.",
            ),
        ),
    )
    base.update(overrides)
    return EditableConstraints.model_validate(base)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = constraints.current(root)
    assert current.version == 1
    assert len(current.disqualifying_conditions) == 2
    assert current.superseded_decisions[0].key == "invented_superseded_decision"


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / constraints.RELATIVE_PATH).read_bytes()
    result = constraints.prepare(root, _edit(), today=date(2026, 9, 7))

    assert (root / constraints.RELATIVE_PATH).read_bytes() == original
    assert "+updated_at: 2026-09-07" in result.unified_diff


def test_prepare_no_toca_nada_si_no_cambio_nada(root: Path) -> None:
    """Solo `updated_at` debería aparecer en el diff cuando se reenvía
    exactamente lo que ya había: es la garantía de que ni los campos
    plegados ni las listas se reflowan sin motivo."""
    result = constraints.prepare(root, _edit(), today=date(2026, 9, 7))
    lines_added = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert lines_added == ["+updated_at: 2026-09-07"]


def test_disqualifying_conditions_edita_el_rule_de_una_existente_en_su_sitio(
    root: Path,
) -> None:
    result = constraints.prepare(
        root,
        _edit(
            disqualifying_conditions=(
                DisqualifyingConditionEdit(
                    id="invented_condition_one",
                    rule="Regla editada de verdad para la primera condición.",
                ),
                DisqualifyingConditionEdit(
                    id="invented_condition_two",
                    rule="Regla inventada de descalificación número dos, "
                    "para el fixture.",
                ),
            )
        ),
        today=date(2026, 9, 7),
    )
    # El campo extra de la fila no tocada por el formulario sigue ahí: no
    # se pierde nada de lo que esta app no gestiona.
    assert "evaluable_from_posting: a_menudo_no" in result.new_text
    assert "affects: >-" in result.new_text
    assert "Regla editada de verdad" in result.new_text
    # La segunda fila, sin cambios, puede salir como contexto del diff pero
    # no como línea añadida o quitada.
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_condition_two" in line for line in changed_lines)
    assert not any("número dos" in line for line in changed_lines)


def test_disqualifying_conditions_anade_una_fila_nueva_sin_tocar_las_existentes(
    root: Path,
) -> None:
    result = constraints.prepare(
        root,
        _edit(
            disqualifying_conditions=(
                DisqualifyingConditionEdit(
                    id="invented_condition_one",
                    rule="Regla inventada de descalificación número uno, "
                    "para el fixture.",
                ),
                DisqualifyingConditionEdit(
                    id="invented_condition_two",
                    rule="Regla inventada de descalificación número dos, "
                    "para el fixture.",
                ),
                DisqualifyingConditionEdit(
                    id="invented_condition_three", rule="Una condición nueva de verdad."
                ),
            )
        ),
        today=date(2026, 9, 7),
    )
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_condition_one" in line for line in changed_lines)
    assert not any("invented_condition_two" in line for line in changed_lines)
    assert "invented_condition_three" in result.new_text
    assert "Una condición nueva de verdad." in result.new_text


def test_disqualifying_conditions_omitir_un_id_no_lo_borra(root: Path) -> None:
    """Alcance de esta rebanada: sin borrar. Omitir un `id` existente en el
    envío no lo elimina del fichero -confirmado con Pablo el 2026-09-07-."""
    result = constraints.prepare(
        root,
        _edit(
            disqualifying_conditions=(
                DisqualifyingConditionEdit(
                    id="invented_condition_one",
                    rule="Regla inventada de descalificación número uno, "
                    "para el fixture.",
                ),
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "invented_condition_two" in result.new_text


def test_superseded_decisions_borra_editar_y_anade(root: Path) -> None:
    result = constraints.prepare(
        root,
        _edit(
            superseded_decisions=(
                SupersededDecisionEdit(
                    key="invented_superseded_decision",
                    text="Texto editado de verdad para esta decisión.",
                ),
                SupersededDecisionEdit(
                    key="una_decision_nueva", text="Una decisión sustituida nueva."
                ),
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "Texto editado de verdad" in result.new_text
    assert "una_decision_nueva" in result.new_text

    validated = constraints.write(
        root, _edit(superseded_decisions=()), today=date(2026, 9, 7)
    )
    assert validated.validated.superseded_decisions == ()
    assert "superseded_decisions:" in validated.new_text


def test_hard_constraints_no_puede_quedar_vacio() -> None:
    with pytest.raises(ValueError, match="hard_constraints|at least 1"):
        EditableConstraints.model_validate(
            dict(
                hard_constraints=(),
                current_known_constraints=CurrentKnownConstraints(
                    timing="transition_during_2026",
                    spain_salary_floor_gross_eur=30000,
                    relocation="accepted",
                    visa_sponsorship="accepted",
                    eu_work_authorization=True,
                ),
                sector_policy=SectorPolicy(excluded_industries=(), rule="r", note="n"),
                disqualifying_conditions=(
                    DisqualifyingConditionEdit(id="x", rule="y"),
                ),
                accepted_conditions=AcceptedConditions(
                    on_call_and_shift_work="aceptado", high_intensity="h"
                ),
                pending_decisions=(),
                superseded_decisions=(),
            )
        )


def test_disqualifying_conditions_rechaza_id_repetido() -> None:
    with pytest.raises(ValueError, match="repite id"):
        EditableConstraints.model_validate(
            dict(
                hard_constraints=("no_fabricated_claims",),
                current_known_constraints=CurrentKnownConstraints(
                    timing="transition_during_2026",
                    spain_salary_floor_gross_eur=30000,
                    relocation="accepted",
                    visa_sponsorship="accepted",
                    eu_work_authorization=True,
                ),
                sector_policy=SectorPolicy(excluded_industries=(), rule="r", note="n"),
                disqualifying_conditions=(
                    DisqualifyingConditionEdit(id="x", rule="y"),
                    DisqualifyingConditionEdit(id="x", rule="z"),
                ),
                accepted_conditions=AcceptedConditions(
                    on_call_and_shift_work="aceptado", high_intensity="h"
                ),
                pending_decisions=(),
                superseded_decisions=(),
            )
        )


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    path = root / constraints.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 1", "version: 0"))

    with pytest.raises(constraints.ConstraintsValidationError):
        constraints.prepare(root, _edit(), today=date(2026, 9, 7))

    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(pending_decisions=("otra_decision_pendiente",))
    constraints.write(root, edit, today=date(2026, 9, 7))

    reread = constraints.current(root)
    assert reread.pending_decisions == ("otra_decision_pendiente",)
    assert reread.updated_at == date(2026, 9, 7)
    assert reread.version == 1
