"""Modelos Pydantic para las fuentes de datos del generador de CV.

Todos los modelos usan ``extra="allow"`` en los bloques narrativos del
repositorio privado (auditoría, notas, justificaciones) para no romperse
cuando ese repositorio añada campos que el generador no necesita leer. Los
campos que el generador sí usa se declaran explícitos y obligatorios.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Bullet(BaseModel):
    model_config = ConfigDict(extra="allow")

    bullet_id: str
    text_en: str
    evidence_status: str
    cv_usage: str
    role_variants: list[str]


class BulletBankPolicy(BaseModel):
    model_config = ConfigDict(extra="allow")

    allowed_contribution_verbs: list[str]
    blocked_ownership_verbs: list[str]


class BulletBank(BaseModel):
    model_config = ConfigDict(extra="allow")

    policy: BulletBankPolicy
    bullets: list[Bullet]

    def bullets_by_id(self) -> dict[str, Bullet]:
        return {bullet.bullet_id: bullet for bullet in self.bullets}


class SkillRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    label: str
    value: str


class VariantContent(BaseModel):
    model_config = ConfigDict(extra="allow")

    display_name: str
    use_when: str
    profile: str
    skills: list[SkillRow]


class RoleVariantContent(BaseModel):
    model_config = ConfigDict(extra="allow")

    variants: dict[str, VariantContent]


class ContributionLanguageRules(BaseModel):
    model_config = ConfigDict(extra="allow")

    allowed: list[str]
    blocked_without_specific_confirmation: list[str]


class ClaimRules(BaseModel):
    model_config = ConfigDict(extra="allow")

    professional_contribution_language: ContributionLanguageRules


class BaseVariantConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    target_roles: list[str]
    display_name: str | None = None
    status: str | None = None
    candidate_bullet_priority: list[str] | None = None


class CvVariantsConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    claim_rules: ClaimRules
    base_variants: dict[str, BaseVariantConfig]
