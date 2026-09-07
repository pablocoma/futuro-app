"""`project_catalog.py`: aplicar una edición, validarla, calcular el diff, y
solo escribir cuando se pide. Nada de git aquí -eso ya lo prueba
`test_data_repo_write_git_ops.py`-, solo el fichero.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from futuro_api.data_repo_write import project_catalog
from futuro_api.data_repo_write.models import EditableProjectCatalog, ProjectEdit
from futuro_api.data_repo_write.vocabularies import BulletEvidenceStatus, ProjectCvUsage

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _professional(**overrides: object) -> ProjectEdit:
    base: dict[str, object] = dict(
        project_id="invented_project_professional",
        safe_name="Invented Professional Project",
        evidence_status=BulletEvidenceStatus.VERIFIED,
        cv_usage=ProjectCvUsage.CONDITIONAL,
        interview_usage=ProjectCvUsage.CONDITIONAL,
        pending_confirmations=("invented_pending_confirmation",),
    )
    base.update(overrides)
    return ProjectEdit.model_validate(base)


def _academic(**overrides: object) -> ProjectEdit:
    base: dict[str, object] = dict(
        project_id="invented_project_academic",
        safe_name="Invented Academic Project",
        evidence_status=BulletEvidenceStatus.PUBLISHABLE,
        cv_usage=ProjectCvUsage.ELIGIBLE,
        interview_usage=ProjectCvUsage.ELIGIBLE,
        pending_confirmations=(),
    )
    base.update(overrides)
    return ProjectEdit.model_validate(base)


def _edit(**overrides: object) -> EditableProjectCatalog:
    base: dict[str, object] = dict(projects=(_professional(), _academic()))
    base.update(overrides)
    return EditableProjectCatalog.model_validate(base)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = project_catalog.current(root)
    assert current.version == 1
    assert current.project_id_set == {
        "invented_project_professional",
        "invented_project_academic",
    }


def test_prepare_no_toca_nada_si_no_cambio_nada(root: Path) -> None:
    result = project_catalog.prepare(root, _edit(), today=date(2026, 9, 7))
    lines_added = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert lines_added == ["+updated_at: 2026-09-07"]


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / project_catalog.RELATIVE_PATH).read_bytes()
    project_catalog.prepare(root, _edit(), today=date(2026, 9, 7))
    assert (root / project_catalog.RELATIVE_PATH).read_bytes() == original


def test_edita_una_fila_existente_sin_tocar_la_otra(root: Path) -> None:
    result = project_catalog.prepare(
        root,
        _edit(
            projects=(
                _professional(
                    safe_name="Renamed Professional Project",
                    evidence_status=BulletEvidenceStatus.PUBLISHABLE,
                ),
                _academic(),
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "Renamed Professional Project" in result.new_text
    # El resto de la fila -estructural, no gestionado por el formulario-
    # sigue intacto.
    assert "source_type: professional" in result.new_text
    assert (
        "canonical_source: profile/project_audits/invented_project_professional.md"
        in result.new_text
    )
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_project_academic" in line for line in changed_lines)


def test_pending_confirmations_editable_por_fila(root: Path) -> None:
    result = project_catalog.prepare(
        root,
        _edit(
            projects=(
                _professional(pending_confirmations=()),
                _academic(pending_confirmations=("a_new_confirmation",)),
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "a_new_confirmation" in result.new_text


def test_projects_debe_declarar_exactamente_los_existentes(root: Path) -> None:
    with pytest.raises(project_catalog.ProjectCatalogValidationError, match="faltan"):
        project_catalog.prepare(
            root, _edit(projects=(_professional(),)), today=date(2026, 9, 7)
        )


def test_projects_rechaza_un_project_id_desconocido(root: Path) -> None:
    with pytest.raises(project_catalog.ProjectCatalogValidationError, match="sobran"):
        project_catalog.prepare(
            root,
            _edit(
                projects=(
                    _professional(),
                    _academic(),
                    _professional(project_id="a_new_project"),
                )
            ),
            today=date(2026, 9, 7),
        )


def test_projects_rechaza_project_id_repetido() -> None:
    with pytest.raises(ValueError, match="repite project_id"):
        EditableProjectCatalog(projects=(_professional(), _professional()))


def test_cv_usage_rechaza_el_vocabulario_de_bullets(root: Path) -> None:
    """`ProjectCvUsage` no es `BulletCvUsage`: el valor real de un bullet
    elegible no es un `cv_usage` válido para un proyecto."""
    with pytest.raises(ValueError):
        ProjectEdit.model_validate(
            {
                "project_id": "invented_project_professional",
                "safe_name": "x",
                "evidence_status": "verified",
                "cv_usage": "eligible_with_internal_policy_check",
                "interview_usage": "eligible",
            }
        )


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    path = root / project_catalog.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 1", "version: 0"))

    with pytest.raises(project_catalog.ProjectCatalogValidationError):
        project_catalog.prepare(root, _edit(), today=date(2026, 9, 7))

    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(
        projects=(
            _professional(safe_name="Rewritten Professional Project"),
            _academic(),
        )
    )
    project_catalog.write(root, edit, today=date(2026, 9, 7))

    reread = project_catalog.current(root)
    assert reread.updated_at == date(2026, 9, 7)
    project = next(
        p for p in reread.projects if p.project_id == "invented_project_professional"
    )
    assert project.safe_name == "Rewritten Professional Project"
    # Bloques fijos -no gestionados por el formulario- sobreviven intactos.
    assert "allowed_evidence_statuses" in reread.rules
    assert "items" in reread.discovery_backlog
