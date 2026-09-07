"""`bullet_bank.py`: aplicar una edición, validarla -incluidas las
`claim_rules` cruzadas contra `config/cv_variants.yaml`-, calcular el diff,
y solo escribir cuando se pide. Nada de git aquí -eso ya lo prueba
`test_data_repo_write_git_ops.py`-, solo el fichero.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from futuro_api.data_repo_write import bullet_bank
from futuro_api.data_repo_write.models import BulletEdit, EditableBulletBank
from futuro_api.data_repo_write.vocabularies import BulletCvUsage, BulletEvidenceStatus

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "data_repo_write"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def _edit(**overrides: object) -> EditableBulletBank:
    """Mismos dos bullets que el fixture, tal como saldría del formulario
    -no se lee el fichero: mismo criterio que `_edit()` en
    `test_data_repo_write_constraints.py`, para poder probar una edición
    contra un fichero que el propio test ha corrompido a mano."""
    base: dict[str, object] = dict(
        bullets=(
            BulletEdit(
                bullet_id="invented_bullet_one",
                text_en="Contributed to building an invented internal tool "
                "for the fixture.",
                evidence_status=BulletEvidenceStatus.VERIFIED,
                cv_usage=BulletCvUsage.ELIGIBLE_WITH_INTERNAL_POLICY_CHECK,
            ),
            BulletEdit(
                bullet_id="invented_bullet_two",
                text_en="Explored an early prototype for the fixture, "
                "not yet confirmed.",
                evidence_status=BulletEvidenceStatus.CANDIDATE,
                cv_usage=BulletCvUsage.BLOCKED,
            ),
        )
    )
    base.update(overrides)
    return EditableBulletBank.model_validate(base)


def test_current_lee_y_valida_el_fichero(root: Path) -> None:
    current = bullet_bank.current(root)
    assert current.version == 1
    assert len(current.bullets) == 2
    assert current.bullets[0].bullet_id == "invented_bullet_one"


def test_prepare_no_toca_nada_si_no_cambio_nada(root: Path) -> None:
    """Solo `updated_at` debería aparecer en el diff cuando se reenvía
    exactamente lo que ya había."""
    result = bullet_bank.prepare(root, _edit(), today=date(2026, 9, 7))
    lines_added = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert lines_added == ["+updated_at: 2026-09-07"]


def test_prepare_no_escribe_nada(root: Path) -> None:
    original = (root / bullet_bank.RELATIVE_PATH).read_bytes()
    bullet_bank.prepare(root, _edit(), today=date(2026, 9, 7))
    assert (root / bullet_bank.RELATIVE_PATH).read_bytes() == original


def test_edita_text_en_de_una_fila_existente_en_su_sitio(root: Path) -> None:
    result = bullet_bank.prepare(
        root,
        _edit(
            bullets=(
                BulletEdit(
                    bullet_id="invented_bullet_one",
                    text_en="Worked on an edited invented tool for the fixture.",
                    evidence_status=BulletEvidenceStatus.VERIFIED,
                    cv_usage=BulletCvUsage.ELIGIBLE_WITH_INTERNAL_POLICY_CHECK,
                ),
                BulletEdit(
                    bullet_id="invented_bullet_two",
                    text_en="Explored an early prototype for the fixture, "
                    "not yet confirmed.",
                    evidence_status=BulletEvidenceStatus.CANDIDATE,
                    cv_usage=BulletCvUsage.BLOCKED,
                ),
            )
        ),
        today=date(2026, 9, 7),
    )
    assert "Worked on an edited invented tool" in result.new_text
    # El resto de campos de la fila, no gestionados por el formulario,
    # sigue intacto.
    assert (
        "confidentiality_status: user_approved_anonymized_2026_01_01" in result.new_text
    )
    assert "project_id: invented_project" in result.new_text
    # La segunda fila, sin cambios, no aparece como línea tocada.
    changed_lines = [
        line
        for line in result.unified_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    assert not any("invented_bullet_two" in line for line in changed_lines)


def test_anade_un_bullet_nuevo_sin_tocar_los_existentes(root: Path) -> None:
    result = bullet_bank.prepare(
        root,
        _edit(
            bullets=_edit().bullets
            + (
                BulletEdit(
                    bullet_id="invented_bullet_three",
                    text_en="Worked on a brand new invented thing for the fixture.",
                    evidence_status=BulletEvidenceStatus.CANDIDATE,
                    cv_usage=BulletCvUsage.BLOCKED,
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
    assert not any("invented_bullet_one" in line for line in changed_lines)
    assert not any("invented_bullet_two" in line for line in changed_lines)
    assert "invented_bullet_three" in result.new_text
    # Sin confirmación de confidencialidad fabricada para una fila nueva.
    assert "confidentiality_status: null" in result.new_text
    assert "project_id: null" in result.new_text


def test_omitir_un_bullet_id_no_lo_borra(root: Path) -> None:
    kept = tuple(b for b in _edit().bullets if b.bullet_id != "invented_bullet_two")
    result = bullet_bank.prepare(
        root, EditableBulletBank(bullets=kept), today=date(2026, 9, 7)
    )
    assert "invented_bullet_two" in result.new_text


def test_bullets_rechaza_bullet_id_repetido() -> None:
    with pytest.raises(ValueError, match="repite bullet_id"):
        EditableBulletBank(
            bullets=(
                BulletEdit(
                    bullet_id="x",
                    text_en="Contributed to x.",
                    evidence_status=BulletEvidenceStatus.VERIFIED,
                    cv_usage=BulletCvUsage.BLOCKED,
                ),
                BulletEdit(
                    bullet_id="x",
                    text_en="Worked on x again.",
                    evidence_status=BulletEvidenceStatus.VERIFIED,
                    cv_usage=BulletCvUsage.BLOCKED,
                ),
            )
        )


def test_evidence_status_rechaza_valor_desconocido() -> None:
    with pytest.raises(ValueError):
        BulletEdit.model_validate(
            {
                "bullet_id": "x",
                "text_en": "Contributed to x.",
                "evidence_status": "not_a_real_status",
                "cv_usage": "blocked",
            }
        )


def test_claim_rules_rechaza_verbo_bloqueado_en_un_bullet_elegible(root: Path) -> None:
    """`invented_bullet_one` es `verified` + `eligible_with_internal_policy_check`:
    su texto sí se valida contra `claim_rules` de `config/cv_variants.yaml`."""
    edit = _edit(
        bullets=(
            BulletEdit(
                bullet_id="invented_bullet_one",
                text_en="Contributed to and owned the invented tool entirely.",
                evidence_status=BulletEvidenceStatus.VERIFIED,
                cv_usage=BulletCvUsage.ELIGIBLE_WITH_INTERNAL_POLICY_CHECK,
            ),
            _edit().bullets[1],
        )
    )
    with pytest.raises(bullet_bank.BulletBankValidationError, match="ownership"):
        bullet_bank.prepare(root, edit, today=date(2026, 9, 7))


def test_claim_rules_no_se_aplica_a_un_bullet_no_elegible(root: Path) -> None:
    """`invented_bullet_two` es `candidate` + `blocked`: su texto puede
    llevar un verbo bloqueado sin que la validación lo rechace, porque
    todavía no es elegible para un CV."""
    edit = _edit(
        bullets=(
            _edit().bullets[0],
            BulletEdit(
                bullet_id="invented_bullet_two",
                text_en="Led an early prototype for the fixture, not yet confirmed.",
                evidence_status=BulletEvidenceStatus.CANDIDATE,
                cv_usage=BulletCvUsage.BLOCKED,
            ),
        )
    )
    result = bullet_bank.prepare(root, edit, today=date(2026, 9, 7))
    assert "Led an early prototype" in result.new_text


def test_claim_rules_exige_verbo_de_contribucion_permitido(root: Path) -> None:
    edit = _edit(
        bullets=(
            BulletEdit(
                bullet_id="invented_bullet_one",
                text_en="Managed the invented team.",
                evidence_status=BulletEvidenceStatus.VERIFIED,
                cv_usage=BulletCvUsage.ELIGIBLE_WITH_INTERNAL_POLICY_CHECK,
            ),
            _edit().bullets[1],
        )
    )
    with pytest.raises(
        bullet_bank.BulletBankValidationError, match="verbo de contribución"
    ):
        bullet_bank.prepare(root, edit, today=date(2026, 9, 7))


def test_marcar_un_bullet_como_elegible_dispara_la_validacion(root: Path) -> None:
    """`invented_bullet_two` empieza por "Explored", que no es un verbo de
    contribución permitido; marcarlo como elegible (aunque su texto no
    cambie) sí debe activar la validación cruzada."""
    edit = _edit(
        bullets=(
            _edit().bullets[0],
            BulletEdit(
                bullet_id="invented_bullet_two",
                text_en="Explored an early prototype for the fixture, "
                "not yet confirmed.",
                evidence_status=BulletEvidenceStatus.VERIFIED,
                cv_usage=BulletCvUsage.ELIGIBLE_WITH_INTERNAL_POLICY_CHECK,
            ),
        )
    )
    with pytest.raises(bullet_bank.BulletBankValidationError):
        bullet_bank.prepare(root, edit, today=date(2026, 9, 7))


def test_prepare_revalida_el_documento_entero_no_solo_lo_editado(root: Path) -> None:
    path = root / bullet_bank.RELATIVE_PATH
    path.write_text(path.read_text().replace("version: 1", "version: 0"))

    with pytest.raises(bullet_bank.BulletBankValidationError):
        bullet_bank.prepare(root, _edit(), today=date(2026, 9, 7))

    assert "version: 0" in path.read_text()


def test_write_escribe_y_el_resultado_se_vuelve_a_leer_igual(root: Path) -> None:
    edit = _edit(
        bullets=(
            BulletEdit(
                bullet_id="invented_bullet_one",
                text_en="Contributed to a rewritten tool.",
                evidence_status=BulletEvidenceStatus.VERIFIED,
                cv_usage=BulletCvUsage.ELIGIBLE_WITH_INTERNAL_POLICY_CHECK,
            ),
            _edit().bullets[1],
        )
    )
    bullet_bank.write(root, edit, today=date(2026, 9, 7))

    reread = bullet_bank.current(root)
    assert reread.updated_at == date(2026, 9, 7)
    assert reread.bullets[0].text_en == "Contributed to a rewritten tool."
    # `policy` -bloque fijo, no gestionado por el formulario- sobrevive
    # intacto.
    assert "status_claims_confirmed_2026_08_14" in reread.policy
