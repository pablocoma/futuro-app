from pathlib import Path

import pytest

from cv_builder.build import BuildError, build_all, load_sources
from cv_builder.claim_rules import ClaimRuleViolation

FIXTURES = Path(__file__).parent / "fixtures"
MASTER = FIXTURES / "master.tex.jinja2"
BULLET_BANK = FIXTURES / "bullet_bank.yaml"
ROLE_CONTENT = FIXTURES / "role_variant_content.yaml"
VARIANTS_CONFIG = FIXTURES / "cv_variants.yaml"


def test_build_all_writes_expected_variant(tmp_path: Path) -> None:
    sources = load_sources(MASTER, BULLET_BANK, ROLE_CONTENT, VARIANTS_CONFIG)
    built = build_all(sources, tmp_path)

    assert built == ["widget_maker"]

    tex = (tmp_path / "widget_maker" / "widget_maker.tex").read_text()
    expected = (FIXTURES / "expected" / "widget_maker.tex").read_text()
    assert tex == expected

    readme = (tmp_path / "widget_maker" / "README.md").read_text()
    assert "Widget Maker" in readme
    assert "widget_engineer" in readme
    assert "Contributed to client-facing delivery" in readme


def test_status_variant_is_skipped(tmp_path: Path) -> None:
    sources = load_sources(MASTER, BULLET_BANK, ROLE_CONTENT, VARIANTS_CONFIG)
    build_all(sources, tmp_path)

    assert not (tmp_path / "unreleased_variant").exists()


def test_unknown_bullet_id_aborts_build(tmp_path: Path) -> None:
    sources = load_sources(
        MASTER,
        BULLET_BANK,
        ROLE_CONTENT,
        FIXTURES / "broken" / "cv_variants_missing_bullet.yaml",
    )

    with pytest.raises(BuildError, match="totally_unknown_bullet"):
        build_all(sources, tmp_path)

    assert not any(tmp_path.iterdir())


def test_claim_violation_aborts_build(tmp_path: Path) -> None:
    sources = load_sources(
        MASTER,
        BULLET_BANK,
        ROLE_CONTENT,
        FIXTURES / "broken" / "cv_variants_claim_violation.yaml",
    )

    with pytest.raises(ClaimRuleViolation, match="ownership_violation"):
        build_all(sources, tmp_path)

    assert not any(tmp_path.iterdir())
