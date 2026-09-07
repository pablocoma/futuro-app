"""`role_variant_content.py`: aplicar una edición, validarla, calcular el
diff, y solo escribir cuando se pide. Nada de git aquí -eso ya lo prueba
`test_data_repo_write_git_ops.py`-, solo el fichero.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from futuro_api.data_repo_write import role_variant_content
from futuro_api.data_repo_write.models import (
    EditableRoleVariantContent,
    SkillRowEdit,
    VariantContent,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _variant_one(**overrides: object) -> VariantContent:
    base: dict[str, object] = dict(
        display_name="Invented Variant One",
        use_when="Nota inventada de cuándo usar esta variante, para el fixture.",
        profile="Perfil inventado para la variante uno, sin ningún dato real.",
        skills=(
            SkillRowEdit(label="Programming", value="Invented, Language"),
            SkillRowEdit(label="Tools", value="Invented Tool A, Invented Tool B"),
        ),
    )
    base.update(overrides)
    return VariantContent.model_validate(base)


def _variant_two(**overrides: object) -> VariantContent:
    base: dict[str, object] = dict(
        display_name="Invented Variant Two",
        use_when="Otra nota inventada de cuándo usar esta variante, para el fixture.",
        profile="Perfil inventado para la variante dos, sin ningún dato real.",
        skills=(SkillRowEdit(label="Programming", value="Invented, Language"),),
    )
    base.update(overrides)
    return VariantContent.model_validate(base)


def _edit(**overrides: VariantContent) -> EditableRoleVariantContent:
    variants = {
        "invented_variant_one": _variant_one(),
        "invented_variant_two": _variant_two(),
    }
    variants.update(overrides)
    return EditableRoleVariantContent(variants=variants)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = role_variant_content.current(root)
    assert current.version == 1
    assert set(current.variants) == {"invented_variant_one", "invented_variant_two"}


def test_prepare_no_toca_nada_si_no_cambio_nada(root: Path) -> None:
    result = role_variant_content.prepare(root, _edit(), today=date(2026, 9, 7))
    lines_added = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert lines_added == ["+updated_at: 2026-09-07"]


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / role_variant_content.RELATIVE_PATH).read_bytes()
    role_variant_content.prepare(root, _edit(), today=date(2026, 9, 7))
    assert (root / role_variant_content.RELATIVE_PATH).read_bytes() == original


def test_edita_profile_de_una_variante_en_su_sitio_sin_tocar_la_otra(
    root: Path,
) -> None:
    result = role_variant_content.prepare(
        root,
        _edit(
            invented_variant_one=_variant_one(
                profile="Perfil editado de verdad para el fixture."
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "Perfil editado de verdad" in result.new_text
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_variant_two" in line for line in changed_lines)
    assert not any("Invented Tool" in line for line in changed_lines)


def test_edita_una_fila_de_skills_existente_sin_ensuciar_las_demas(
    root: Path,
) -> None:
    """Casada por posición: cambiar la segunda fila no toca la primera ni
    la línea en blanco que separa esta variante de la siguiente."""
    result = role_variant_content.prepare(
        root,
        _edit(
            invented_variant_one=_variant_one(
                skills=(
                    SkillRowEdit(label="Programming", value="Invented, Language"),
                    SkillRowEdit(label="Tools", value="Invented Tool A, edited"),
                )
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "Invented Tool A, edited" in result.new_text
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    # Ni la línea en blanco ni "Programming" cambian: solo `updated_at` y
    # la fila tocada.
    assert changed_lines == [
        "-updated_at: 2026-01-01",
        "+updated_at: 2026-09-07",
        "-        value: Invented Tool A, Invented Tool B",
        "+        value: Invented Tool A, edited",
    ]


def test_anade_y_quita_filas_de_skills(root: Path) -> None:
    added = role_variant_content.prepare(
        root,
        _edit(
            invented_variant_two=_variant_two(
                skills=(
                    SkillRowEdit(label="Programming", value="Invented, Language"),
                    SkillRowEdit(label="Extra", value="Extra value"),
                )
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "Extra value" in added.new_text

    removed = role_variant_content.prepare(
        root,
        _edit(invented_variant_one=_variant_one(skills=(_variant_one().skills[0],))),
        today=date(2026, 9, 7),
    )
    assert "Invented Tool A" not in removed.new_text


def test_variants_debe_declarar_exactamente_las_claves_existentes(root: Path) -> None:
    with pytest.raises(
        role_variant_content.RoleVariantContentValidationError, match="faltan"
    ):
        role_variant_content.prepare(
            root,
            EditableRoleVariantContent(
                variants={"invented_variant_one": _variant_one()}
            ),
            today=date(2026, 9, 7),
        )


def test_variants_rechaza_una_clave_desconocida(root: Path) -> None:
    with pytest.raises(
        role_variant_content.RoleVariantContentValidationError, match="sobran"
    ):
        role_variant_content.prepare(
            root,
            EditableRoleVariantContent(
                variants={
                    "invented_variant_one": _variant_one(),
                    "invented_variant_two": _variant_two(),
                    "a_new_variant": _variant_one(),
                }
            ),
            today=date(2026, 9, 7),
        )


def test_skills_no_puede_quedar_vacio() -> None:
    with pytest.raises(ValueError, match="at least 1|skills"):
        VariantContent.model_validate(
            {
                "display_name": "x",
                "use_when": "y",
                "profile": "z",
                "skills": [],
            }
        )


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    path = root / role_variant_content.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 1", "version: 0"))

    with pytest.raises(role_variant_content.RoleVariantContentValidationError):
        role_variant_content.prepare(root, _edit(), today=date(2026, 9, 7))

    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(
        invented_variant_one=_variant_one(display_name="Renamed Invented Variant")
    )
    role_variant_content.write(root, edit, today=date(2026, 9, 7))

    reread = role_variant_content.current(root)
    assert reread.updated_at == date(2026, 9, 7)
    assert reread.variants["invented_variant_one"].display_name == (
        "Renamed Invented Variant"
    )
