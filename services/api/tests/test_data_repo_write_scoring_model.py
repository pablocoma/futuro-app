"""`scoring_model.py`: aplicar una edición, validarla, calcular el diff, y
solo escribir cuando se pide. Nada de git aquí -eso ya lo prueba
`test_data_repo_write_git_ops.py`-, solo el fichero.

Sin validación cruzada con otros ficheros -a diferencia de
`cv_variants.py`-: ninguna referencia de `scoring_model.yaml` a otro
fichero es un identificador que el código resuelva.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from futuro_api.data_repo_write import scoring_model
from futuro_api.data_repo_write.models import (
    BaselineEdit,
    DimensionEdit,
    EditableScoringModel,
    GateEdit,
    LabeledTextRow,
    PortfolioPolicyEdit,
    ProbabilityBandsEdit,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _row(label: str, text: str) -> LabeledTextRow:
    return LabeledTextRow(label=label, text=text)


def _dimension_one(**overrides: object) -> DimensionEdit:
    base: dict[str, object] = dict(
        name="invented_dimension_one",
        weight=30,
        anchors=(
            _row("assumption", "Supuesto inventado de la primera dimensión."),
            _row("0", "Ancla inventada de nivel 0 para la primera dimensión."),
            _row("1", "Ancla inventada de nivel 1 para la primera dimensión."),
            _row("3", "Ancla inventada de nivel 3 para la primera dimensión."),
            _row("5", "Ancla inventada de nivel 5 para la primera dimensión."),
        ),
    )
    base.update(overrides)
    return DimensionEdit.model_validate(base)


def _dimension_two(**overrides: object) -> DimensionEdit:
    base: dict[str, object] = dict(
        name="invented_dimension_two",
        weight=25,
        anchors=(
            _row("0", "Ancla inventada de nivel 0 para la segunda dimensión."),
            _row("3", "Ancla inventada de nivel 3 para la segunda dimensión."),
            _row("5", "Ancla inventada de nivel 5 para la segunda dimensión."),
        ),
    )
    base.update(overrides)
    return DimensionEdit.model_validate(base)


def _dimension_three(**overrides: object) -> DimensionEdit:
    base: dict[str, object] = dict(
        name="invented_dimension_three",
        weight=45,
        anchors=(
            _row("note", "Nota inventada de la tercera dimensión."),
            _row("0", "Ancla inventada de nivel 0 para la tercera dimensión."),
            _row("1", "Ancla inventada de nivel 1 para la tercera dimensión."),
            _row("3", "Ancla inventada de nivel 3 para la tercera dimensión."),
            _row("5", "Ancla inventada de nivel 5 para la tercera dimensión."),
        ),
    )
    base.update(overrides)
    return DimensionEdit.model_validate(base)


def _gate_one(**overrides: object) -> GateEdit:
    base: dict[str, object] = dict(
        name="invented_gate_one",
        rows=(
            _row("pass", "Criterio inventado de paso del primer filtro."),
            _row("fail", "Criterio inventado de fallo del primer filtro."),
        ),
    )
    base.update(overrides)
    return GateEdit.model_validate(base)


def _gate_two(**overrides: object) -> GateEdit:
    base: dict[str, object] = dict(
        name="invented_gate_two",
        rows=(
            _row("context", "Contexto inventado del segundo filtro."),
            _row("pass_a", "Criterio inventado A del segundo filtro."),
            _row("pass_b", "Criterio inventado B del segundo filtro."),
            _row("pending", "Criterio inventado de pendiente del segundo filtro."),
        ),
    )
    base.update(overrides)
    return GateEdit.model_validate(base)


def _baseline(**overrides: object) -> BaselineEdit:
    base: dict[str, object] = dict(
        gross_annual_eur=24000,
        payments_per_year=12,
        net_monthly_eur=1600,
        net_annual_eur=19200,
        living_costs_monthly_eur=(350, 450),
        annual_savings_eur=(13800, 14800),
        reference_savings_eur=14000,
        savings_rate=0.70,
        cause="Motivo inventado de por qué ahorra tanto quedándose donde está.",
        implication=(
            "Implicación inventada de lo que un puesto internacional tendría "
            "que batir para compensar la mudanza."
        ),
    )
    base.update(overrides)
    return BaselineEdit.model_validate(base)


def _probability_bands(**overrides: object) -> ProbabilityBandsEdit:
    base: dict[str, object] = dict(
        high="Texto inventado de banda de probabilidad alta.",
        medium="Texto inventado de banda de probabilidad media.",
        low="Texto inventado de banda de probabilidad baja.",
        very_low="Texto inventado de banda de probabilidad muy baja.",
    )
    base.update(overrides)
    return ProbabilityBandsEdit.model_validate(base)


def _portfolio_policy(**overrides: object) -> PortfolioPolicyEdit:
    base: dict[str, object] = dict(
        realistic=0.40,
        realistic_stretch=0.35,
        aspirational=0.20,
        experimental=0.05,
        status="descriptive",
        note="Nota inventada de la política de cartera, descriptiva y no prescriptiva.",
    )
    base.update(overrides)
    return PortfolioPolicyEdit.model_validate(base)


def _edit(**overrides: object) -> EditableScoringModel:
    base: dict[str, object] = dict(
        description="Modelo de comparación INVENTADO, harness de escritura.",
        baseline=_baseline(),
        dimensions=(_dimension_one(), _dimension_two(), _dimension_three()),
        gates=(_gate_one(), _gate_two()),
        probability_bands=_probability_bands(),
        minimum_coverage=0.55,
        never_rule="Regla inventada de qué nunca se estima para rellenar una nota.",
        effort_evaluation_order=("skip", "cheap", "full", "standard"),
        portfolio_policy=_portfolio_policy(),
        notes=(
            "Primera nota inventada, de varias líneas para probar que el "
            "plegado sobrevive a una escritura que no la toca.",
            "Segunda nota inventada, más corta.",
        ),
    )
    base.update(overrides)
    return EditableScoringModel.model_validate(base)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = scoring_model.current(root)
    assert current.version == 3
    assert current.baseline_name == "baseline_puerto_inventado"
    assert {d.name for d in current.dimensions} == {
        "invented_dimension_one",
        "invented_dimension_two",
        "invented_dimension_three",
    }
    assert {g.name for g in current.gates} == {"invented_gate_one", "invented_gate_two"}
    assert current.effort_evaluation_order == ("skip", "cheap", "full", "standard")
    # Bloques de solo lectura viajan tal cual.
    assert current.scale["range"] == [0, 5]
    assert "realistic" in current.portfolio_assignment
    assert "required_fields" in current.output


def test_prepare_no_toca_nada_si_no_cambio_nada(root: Path) -> None:
    result = scoring_model.prepare(root, _edit(), today=date(2026, 9, 8))
    lines_added = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    # Solo el `updated_at` del documento se mueve; el de `baseline_*` no,
    # porque ningún campo de la línea base cambió de verdad.
    assert lines_added == ["+updated_at: 2026-09-08"]


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / scoring_model.RELATIVE_PATH).read_bytes()
    scoring_model.prepare(root, _edit(), today=date(2026, 9, 8))
    assert (root / scoring_model.RELATIVE_PATH).read_bytes() == original


def test_editar_el_peso_y_un_ancla_de_una_dimension_sin_tocar_las_otras(
    root: Path,
) -> None:
    result = scoring_model.prepare(
        root,
        _edit(
            dimensions=(
                _dimension_one(
                    weight=35,
                    anchors=(
                        _row(
                            "assumption", "Supuesto inventado de la primera dimensión."
                        ),
                        _row(
                            "0", "Ancla inventada de nivel 0 para la primera dimensión."
                        ),
                        _row(
                            "1", "Ancla inventada de nivel 1 para la primera dimensión."
                        ),
                        _row(
                            "3", "Ancla EDITADA de nivel 3 para la primera dimensión."
                        ),
                        _row(
                            "5", "Ancla inventada de nivel 5 para la primera dimensión."
                        ),
                    ),
                ),
                _dimension_two(),
                _dimension_three(),
            )
        ),
        today=date(2026, 9, 8),
    )
    assert "invented_dimension_one: 35" in result.new_text
    assert "Ancla EDITADA de nivel 3" in result.new_text
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_dimension_two" in line for line in changed_lines)
    assert not any("invented_dimension_three" in line for line in changed_lines)


def test_anade_una_dimension_nueva(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(
            dimensions=(
                _dimension_one(),
                _dimension_two(),
                _dimension_three(),
                DimensionEdit(
                    name="invented_dimension_four",
                    weight=10,
                    anchors=(_row("0", "Ancla nueva de nivel 0"),),
                ),
            )
        ),
        today=date(2026, 9, 8),
    )
    assert "invented_dimension_four: 10" in result.new_text
    assert "Ancla nueva de nivel 0" in result.new_text
    reread = scoring_model.write(
        root,
        _edit(
            dimensions=(
                _dimension_one(),
                _dimension_two(),
                _dimension_three(),
                DimensionEdit(
                    name="invented_dimension_four",
                    weight=10,
                    anchors=(_row("0", "Ancla nueva de nivel 0"),),
                ),
            )
        ),
        today=date(2026, 9, 8),
    )
    assert "invented_dimension_four" in {d.name for d in reread.validated.dimensions}


def test_quita_una_dimension(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(dimensions=(_dimension_one(), _dimension_two())),
        today=date(2026, 9, 8),
    )
    assert "invented_dimension_three" not in result.new_text
    assert {d.name for d in result.validated.dimensions} == {
        "invented_dimension_one",
        "invented_dimension_two",
    }


def test_dimension_rechaza_ancla_sin_ningun_nivel_numerico() -> None:
    with pytest.raises(ValidationError, match="nivel numérico"):
        DimensionEdit(
            name="x",
            weight=10,
            anchors=(_row("assumption", "solo una nota, sin nivel"),),
        )


def test_dimension_rechaza_etiqueta_de_ancla_repetida() -> None:
    with pytest.raises(ValidationError, match="repite la etiqueta"):
        DimensionEdit(
            name="x",
            weight=10,
            anchors=(_row("0", "primera"), _row("0", "segunda")),
        )


def test_rechaza_nombre_de_dimension_repetido() -> None:
    with pytest.raises(ValidationError, match="dimensions repite el nombre"):
        _edit(dimensions=(_dimension_one(), _dimension_one()))


def test_editar_un_gate_sin_tocar_el_otro(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(
            gates=(
                _gate_one(
                    rows=(
                        _row("pass", "Criterio EDITADO de paso del primer filtro."),
                        _row("fail", "Criterio inventado de fallo del primer filtro."),
                    )
                ),
                _gate_two(),
            )
        ),
        today=date(2026, 9, 8),
    )
    assert "Criterio EDITADO de paso" in result.new_text
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_gate_two" in line for line in changed_lines)


def test_anade_y_quita_un_gate(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(
            gates=(
                _gate_one(),
                GateEdit(
                    name="invented_gate_three",
                    rows=(_row("pass", "Criterio nuevo de paso"),),
                ),
            )
        ),
        today=date(2026, 9, 8),
    )
    # `invented_gate_two` sigue mencionado en el comentario de cabecera del
    # fixture -texto libre, no la clave YAML-, así que se comprueba contra
    # el documento ya validado y no contra una búsqueda de texto ingenua.
    assert {g.name for g in result.validated.gates} == {
        "invented_gate_one",
        "invented_gate_three",
    }
    assert "\n  invented_gate_two:\n" not in result.new_text
    assert "invented_gate_three" in result.new_text


def test_gate_rechaza_filas_sin_ningun_criterio() -> None:
    with pytest.raises(ValidationError, match="ningún criterio"):
        GateEdit(
            name="x",
            rows=(_row("context", "solo contexto, sin criterio"),),
        )


def test_editar_la_baseline_sin_tocar_su_updated_at_si_no_cambia(root: Path) -> None:
    result = scoring_model.prepare(root, _edit(), today=date(2026, 9, 8))
    assert "baseline_puerto_inventado" not in "\n".join(
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )


def test_editar_un_campo_de_la_baseline_sí_mueve_su_updated_at(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(baseline=_baseline(gross_annual_eur=26000)),
        today=date(2026, 9, 8),
    )
    assert "gross_annual_eur: 26000" in result.new_text
    added = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert any("updated_at: 2026-09-08" in line for line in added)
    # Las dos líneas `updated_at` -documento y baseline- se mueven a la vez.
    assert len([line for line in added if "updated_at: 2026-09-08" in line]) == 2


def test_baseline_rechaza_rango_decreciente() -> None:
    with pytest.raises(ValidationError, match="debe ir de menor a mayor"):
        _baseline(living_costs_monthly_eur=(500, 400))


def test_minimum_coverage_conserva_el_formato_si_no_cambia(root: Path) -> None:
    result = scoring_model.prepare(root, _edit(), today=date(2026, 9, 8))
    assert "minimum_coverage: 0.55" in result.new_text
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("minimum_coverage" in line for line in changed_lines)


def test_minimum_coverage_editable(root: Path) -> None:
    result = scoring_model.prepare(
        root, _edit(minimum_coverage=0.6), today=date(2026, 9, 8)
    )
    assert "minimum_coverage: 0.6" in result.new_text


def test_effort_evaluation_order_reordenable(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(effort_evaluation_order=("full", "standard", "cheap", "skip")),
        today=date(2026, 9, 8),
    )
    assert "evaluation_order: [full, standard, cheap, skip]" in result.new_text
    # El resto del bloque -documentación de umbrales que decide el código
    # a mano- sobrevive intacto.
    assert "Condición inventada del nivel full" in result.new_text


def test_effort_evaluation_order_rechaza_una_permutacion_incompleta() -> None:
    with pytest.raises(ValidationError, match="effort_evaluation_order"):
        _edit(effort_evaluation_order=("full", "standard", "cheap"))


def test_effort_evaluation_order_rechaza_un_nombre_desconocido() -> None:
    with pytest.raises(ValidationError):
        EditableScoringModel.model_validate(
            {
                **_edit().model_dump(),
                "effort_evaluation_order": ["full", "standard", "cheap", "nope"],
            }
        )


def test_probability_bands_editable_por_texto(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(
            probability_bands=_probability_bands(high="Texto EDITADO de banda alta.")
        ),
        today=date(2026, 9, 8),
    )
    assert "Texto EDITADO de banda alta." in result.new_text


def test_portfolio_policy_editable(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(portfolio_policy=_portfolio_policy(realistic=0.5)),
        today=date(2026, 9, 8),
    )
    assert "realistic: 0.5" in result.new_text


def test_notes_editable_y_se_pliega(root: Path) -> None:
    result = scoring_model.prepare(
        root,
        _edit(notes=("Nota única EDITADA, reemplaza a las dos anteriores.",)),
        today=date(2026, 9, 8),
    )
    assert "Nota única EDITADA" in result.new_text
    assert "Primera nota inventada" not in result.new_text


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    path = root / scoring_model.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 3", "version: 0"))

    with pytest.raises(scoring_model.ScoringModelValidationError):
        scoring_model.prepare(root, _edit(), today=date(2026, 9, 8))

    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(
        dimensions=(_dimension_one(weight=99), _dimension_two(), _dimension_three())
    )
    scoring_model.write(root, edit, today=date(2026, 9, 8))

    reread = scoring_model.current(root)
    assert reread.updated_at == date(2026, 9, 8)
    dimension = next(d for d in reread.dimensions if d.name == "invented_dimension_one")
    assert dimension.weight == 99
    # Bloques de solo lectura -no gestionados por el formulario- sobreviven.
    assert "required_fields" in reread.output
    assert (
        reread.output["effort_tier"]["full"]["when"]
        == "Condición inventada del nivel full."
    )
    assert "rule" in reread.missing_data
