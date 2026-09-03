from pathlib import Path

from cv_builder.render import (
    SkillRowContext,
    VariantRenderContext,
    render_readme,
    render_variant,
)

MASTER = Path(__file__).parent / "fixtures" / "master.tex.jinja2"

CONTEXT = VariantRenderContext(
    variant_id="widget_maker",
    display_name="Widget Maker",
    use_when="Ofertas de fabricación de widgets.",
    target_roles=["widget_engineer"],
    profile="Test engineer profile text.",
    role_bullets=["First bullet text.", "Second bullet text."],
    skill_rows=[
        SkillRowContext(label="Programming", value="Python, SQL"),
        SkillRowContext(label="Testing", value="pytest"),
    ],
)


def test_skill_rows_render_without_stray_whitespace() -> None:
    tex = render_variant(MASTER, CONTEXT)
    assert r"\skillrow{Programming}{Python, SQL}" in tex
    assert r"\skillrow{Testing}{pytest}" in tex
    assert r"\skillrow{ Programming }" not in tex


def test_bullet_items_render_in_order() -> None:
    tex = render_variant(MASTER, CONTEXT)
    first_index = tex.index(r"\item First bullet text.")
    second_index = tex.index(r"\item Second bullet text.")
    assert first_index < second_index


def test_profile_is_substituted() -> None:
    tex = render_variant(MASTER, CONTEXT)
    assert "Test engineer profile text." in tex


def test_fixed_sections_survive_untouched() -> None:
    tex = render_variant(MASTER, CONTEXT)
    assert "Static synthetic project description" in tex
    assert "Static synthetic education facts" in tex
    assert "Static synthetic languages" in tex
    assert "Static synthetic awards" in tex


def test_readme_lists_target_roles_and_bullets() -> None:
    readme = render_readme(CONTEXT)
    assert "`widget_engineer`" in readme
    assert "- First bullet text." in readme
    assert "- Second bullet text." in readme
    assert "- **Programming:** Python, SQL" in readme
    assert "> Test engineer profile text." in readme
