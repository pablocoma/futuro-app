"""`cv_variants.py`: aplicar una edición, validarla -incluida la validación
cruzada contra `professional_bullet_bank.yaml`, `project_catalog.yaml` y
`role_variant_content.yaml`-, calcular el diff, y solo escribir cuando se
pide. Nada de git aquí -eso ya lo prueba `test_data_repo_write_git_ops.py`-,
solo el fichero.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from futuro_api.data_repo_write import cv_variants
from futuro_api.data_repo_write.models import BaseVariantEdit, EditableCvVariants

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _variant_one(**overrides: object) -> BaseVariantEdit:
    base: dict[str, object] = dict(
        target_roles=("invented_role_one",),
        emphasis=("invented_emphasis_one",),
        professional_project_priority=("invented_project_professional",),
        public_project_priority=("invented_project_academic",),
        candidate_bullet_priority=("invented_bullet_one",),
    )
    base.update(overrides)
    return BaseVariantEdit.model_validate(base)


def _variant_two(**overrides: object) -> BaseVariantEdit:
    base: dict[str, object] = dict(
        target_roles=("invented_role_two",),
        emphasis=("invented_emphasis_two",),
        professional_project_priority=("invented_project_professional",),
        public_project_priority=("invented_project_academic",),
        candidate_bullet_priority=("invented_bullet_two",),
    )
    base.update(overrides)
    return BaseVariantEdit.model_validate(base)


def _edit(**overrides: BaseVariantEdit) -> EditableCvVariants:
    variants = {
        "invented_variant_one": _variant_one(),
        "invented_variant_two": _variant_two(),
    }
    variants.update(overrides)
    return EditableCvVariants(base_variants=variants)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = cv_variants.current(root)
    assert current.version == 1
    assert current.active_variant_ids == {
        "invented_variant_one",
        "invented_variant_two",
    }
    assert "invented_variant_blocked" in current.base_variants
    assert current.base_variants["invented_variant_blocked"].status is not None


def test_prepare_no_toca_nada_si_no_cambio_nada(root: Path) -> None:
    result = cv_variants.prepare(root, _edit(), today=date(2026, 9, 7))
    lines_added = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert lines_added == ["+updated_at: 2026-09-07"]


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / cv_variants.RELATIVE_PATH).read_bytes()
    cv_variants.prepare(root, _edit(), today=date(2026, 9, 7))
    assert (root / cv_variants.RELATIVE_PATH).read_bytes() == original


def test_edita_las_listas_de_una_variante_sin_tocar_la_otra(root: Path) -> None:
    result = cv_variants.prepare(
        root,
        _edit(invented_variant_one=_variant_one(emphasis=("edited_emphasis",))),
        today=date(2026, 9, 7),
    )
    assert "edited_emphasis" in result.new_text
    # Los campos atípicos -de solo lectura- sobreviven intactos.
    assert "Invented Variant One Display" in result.new_text
    assert "Nota inventada de variante uno" in result.new_text
    assert "invented_bullet_two" in result.new_text  # exclusive_evidence
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_variant_two" in line for line in changed_lines)
    assert not any("invented_variant_blocked" in line for line in changed_lines)


def test_no_toca_la_variante_bloqueada(root: Path) -> None:
    result = cv_variants.prepare(root, _edit(), today=date(2026, 9, 7))
    assert "invented_blocked_status" in result.new_text
    assert "invented_role_blocked" in result.new_text


def test_base_variants_debe_declarar_exactamente_las_activas(root: Path) -> None:
    with pytest.raises(cv_variants.CvVariantsValidationError, match="faltan"):
        cv_variants.prepare(
            root,
            EditableCvVariants(base_variants={"invented_variant_one": _variant_one()}),
            today=date(2026, 9, 7),
        )


def test_base_variants_rechaza_intentar_editar_la_bloqueada(root: Path) -> None:
    with pytest.raises(cv_variants.CvVariantsValidationError, match="sobran"):
        cv_variants.prepare(
            root,
            _edit(invented_variant_blocked=_variant_one()),
            today=date(2026, 9, 7),
        )


def test_rechaza_bullet_id_desconocido_en_candidate_bullet_priority(root: Path) -> None:
    with pytest.raises(
        cv_variants.CvVariantsValidationError, match="bullet_id que no existe"
    ):
        cv_variants.prepare(
            root,
            _edit(
                invented_variant_one=_variant_one(
                    candidate_bullet_priority=("no_such_bullet",)
                )
            ),
            today=date(2026, 9, 7),
        )


def test_rechaza_project_id_desconocido_en_professional_project_priority(
    root: Path,
) -> None:
    with pytest.raises(
        cv_variants.CvVariantsValidationError, match="project_id que no existe"
    ):
        cv_variants.prepare(
            root,
            _edit(
                invented_variant_one=_variant_one(
                    professional_project_priority=("no_such_project",)
                )
            ),
            today=date(2026, 9, 7),
        )


def test_rechaza_project_id_desconocido_en_public_project_priority(root: Path) -> None:
    with pytest.raises(
        cv_variants.CvVariantsValidationError, match="project_id que no existe"
    ):
        cv_variants.prepare(
            root,
            _edit(
                invented_variant_one=_variant_one(
                    public_project_priority=("no_such_project",)
                )
            ),
            today=date(2026, 9, 7),
        )


def test_rechaza_exclusive_evidence_con_bullet_id_desconocido(root: Path) -> None:
    """`exclusive_evidence` no se edita en esta rebanada, pero se revalida
    igual -misma disciplina que el resto del documento- si el fichero ya
    trae una referencia rota."""
    path = root / cv_variants.RELATIVE_PATH
    path.write_text(path.read_text().replace("invented_bullet_two", "no_such_bullet"))

    with pytest.raises(
        cv_variants.CvVariantsValidationError, match="bullet_id que no existe"
    ):
        cv_variants.prepare(root, _edit(), today=date(2026, 9, 7))


def test_rechaza_role_variant_content_huerfano(root: Path) -> None:
    """Si `role_variant_content.yaml` declarara una clave sin
    `base_variants` activo correspondiente, la escritura debe rechazarla
    -aunque esa clave no forme parte de la edición-."""
    path = root / "cv/content/role_variant_content.yaml"
    orphan = (
        "an_orphan_variant:\n"
        "    display_name: x\n"
        "    use_when: y\n"
        "    profile: z\n"
        "    skills:\n"
        "      - label: a\n"
        "        value: b\n"
        "  invented_variant_two:"
    )
    path.write_text(path.read_text().replace("invented_variant_two:", orphan))

    with pytest.raises(
        cv_variants.CvVariantsValidationError, match="sin base_variants activo"
    ):
        cv_variants.prepare(root, _edit(), today=date(2026, 9, 7))


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    path = root / cv_variants.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 1", "version: 0"))

    with pytest.raises(cv_variants.CvVariantsValidationError):
        cv_variants.prepare(root, _edit(), today=date(2026, 9, 7))

    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(invented_variant_one=_variant_one(emphasis=("rewritten_emphasis",)))
    cv_variants.write(root, edit, today=date(2026, 9, 7))

    reread = cv_variants.current(root)
    assert reread.updated_at == date(2026, 9, 7)
    assert reread.base_variants["invented_variant_one"].emphasis == (
        "rewritten_emphasis",
    )
    # Bloques fijos -no gestionados por el formulario- sobreviven intactos.
    assert "professional_contribution_language" in reread.claim_rules
    assert "identity_and_contact" in reread.fixed_sections
