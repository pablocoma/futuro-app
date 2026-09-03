"""Orquesta la construcción de las variantes de CV: carga fuentes, resuelve
bullets elegibles por variante, renderiza y escribe `.tex` + `README.md`.

Un fallo en cualquier variante aborta el build entero sin escribir nada a
medias: primero se resuelve y valida todo, luego se escribe a disco.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .claim_rules import validate_bullet_eligibility, validate_contribution_language
from .models import BulletBank, CvVariantsConfig, RoleVariantContent
from .render import (
    SkillRowContext,
    VariantRenderContext,
    render_readme,
    render_variant,
)


class BuildError(Exception):
    """Error irrecuperable al construir las variantes; el build se aborta."""


@dataclass(frozen=True)
class BuildSources:
    master_template_path: Path
    bullet_bank: BulletBank
    role_content: RoleVariantContent
    variants_config: CvVariantsConfig


def _read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_sources(
    master_template_path: Path,
    bullet_bank_path: Path,
    role_content_path: Path,
    variants_config_path: Path,
) -> BuildSources:
    bullet_bank = BulletBank.model_validate(_read_yaml(bullet_bank_path))
    role_content = RoleVariantContent.model_validate(_read_yaml(role_content_path))
    variants_config = CvVariantsConfig.model_validate(_read_yaml(variants_config_path))
    return BuildSources(
        master_template_path=master_template_path,
        bullet_bank=bullet_bank,
        role_content=role_content,
        variants_config=variants_config,
    )


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def resolve_variant(
    variant_id: str, sources: BuildSources
) -> VariantRenderContext | None:
    """Contexto de render de una variante, o `None` si se salta (`status`)."""
    config = sources.variants_config.base_variants[variant_id]

    if config.status is not None:
        return None

    if config.candidate_bullet_priority is None:
        raise BuildError(
            f"{variant_id}: no tiene 'status' ni 'candidate_bullet_priority'"
        )

    try:
        content = sources.role_content.variants[variant_id]
    except KeyError as exc:
        raise BuildError(
            f"{variant_id}: no hay contenido en role_variant_content.yaml"
        ) from exc

    bullets_by_id = sources.bullet_bank.bullets_by_id()
    claim_rules = sources.variants_config.claim_rules

    selected_bullets: list[str] = []
    for bullet_id in config.candidate_bullet_priority:
        try:
            bullet = bullets_by_id[bullet_id]
        except KeyError as exc:
            raise BuildError(
                f"{variant_id}: bullet_id desconocido {bullet_id!r}"
            ) from exc
        validate_bullet_eligibility(bullet)
        validate_contribution_language(bullet.bullet_id, bullet.text_en, claim_rules)
        selected_bullets.append(_collapse_whitespace(bullet.text_en))

    return VariantRenderContext(
        variant_id=variant_id,
        display_name=content.display_name,
        use_when=_collapse_whitespace(content.use_when),
        target_roles=list(config.target_roles),
        profile=_collapse_whitespace(content.profile),
        role_bullets=selected_bullets,
        skill_rows=[
            SkillRowContext(label=row.label, value=row.value) for row in content.skills
        ],
    )


def build_all(sources: BuildSources, output_dir: Path) -> list[str]:
    """Resuelve y renderiza todas las variantes; escribe a disco al final.

    Recolecta y valida todo antes de escribir nada, para que un fallo en
    cualquier variante no deje una construcción a medias en disco.
    """
    contexts: dict[str, VariantRenderContext] = {}
    for variant_id in sources.variants_config.base_variants:
        context = resolve_variant(variant_id, sources)
        if context is not None:
            contexts[variant_id] = context

    for variant_id, context in contexts.items():
        variant_dir = output_dir / variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        tex = render_variant(sources.master_template_path, context)
        readme = render_readme(context)
        (variant_dir / f"{variant_id}.tex").write_text(tex, encoding="utf-8")
        (variant_dir / "README.md").write_text(readme, encoding="utf-8")

    return sorted(contexts)
