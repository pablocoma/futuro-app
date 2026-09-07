"""Modelos de validación de escritura, uno por fichero del repositorio
privado. `Objectives` es el primero -M0-; M1-M4 añaden el resto según se
construyan sus rebanadas.

Validan el **resultado** de aplicar una edición, no el documento entero tal
cual: `ruamel.yaml` es quien conserva comentarios y orden en `objectives.py`,
y estos modelos son la puerta de Pydantic que decide si lo que va a quedar
escrito tiene la forma que el fichero promete -toda ella, no solo la parte
que el resto de la aplicación lee hoy-.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from futuro_api.data_repo_write.vocabularies import BulletCvUsage, BulletEvidenceStatus
from futuro_api.offers.vocabularies import RoleFamily

# `OTHER` es el motivo de "esto no encaja en ningún objetivo", no una
# familia que se declare como propia: no tiene sentido en `objectives.yaml`.
_DECLARABLE_ROLE_FAMILIES = frozenset(RoleFamily) - {RoleFamily.OTHER}


class Transition(BaseModel):
    target_year: int = Field(gt=2000, lt=2100)
    urgency: str = Field(min_length=1)
    expected_tenure_years: tuple[int, int]

    @model_validator(mode="after")
    def _rango_creciente(self) -> Transition:
        low, high = self.expected_tenure_years
        if low > high:
            raise ValueError(
                "expected_tenure_years debe ir de menor a mayor: "
                f"[{low}, {high}] no lo es"
            )
        return self


class PrimaryObjective(BaseModel):
    statement: str = Field(min_length=1)


class RoleFamilies(BaseModel):
    # Vocabulario de código, no libre: `RoleFamily` es lo que
    # `offers/classification` usa para decidir si una oferta cae dentro del
    # objetivo. Un nombre que no coincida no rompería nada al guardar, pero
    # dejaría una familia inalcanzable en silencio -ninguna oferta la
    # tocaría nunca-, que es justo el fallo que este modelo existe para
    # atrapar al escribir y no al puntuar.
    core: tuple[str, ...] = Field(min_length=1)
    exploratory: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _vocabulario_conocido_y_sin_duplicados(self) -> RoleFamilies:
        declared = list(self.core) + list(self.exploratory)
        unknown = sorted(
            {name for name in declared if name not in _DECLARABLE_ROLE_FAMILIES}
        )
        if unknown:
            raise ValueError(
                f"role_families no reconoce {unknown}; las familias válidas "
                f"son {sorted(f.value for f in _DECLARABLE_ROLE_FAMILIES)}"
            )
        duplicated = sorted({name for name in declared if declared.count(name) > 1})
        if duplicated:
            raise ValueError(
                f"role_families repite {duplicated} entre «core» y "
                "«exploratory», o dentro de la misma lista"
            )
        return self


class EditableObjectives(BaseModel):
    """Las cuatro claves que el formulario edita.

    `version` y `updated_at` se quedan fuera a propósito: la primera no la
    toca esta rebanada -no hay ninguna regla de cuándo subirla, a
    diferencia de `scoring_model.yaml`, que sí cambia de comportamiento
    entre versiones- y la segunda la estampa el propio backend con la
    fecha de la escritura, no algo que se rellene a mano cada vez.
    """

    transition: Transition
    primary_objective: PrimaryObjective
    success_dimensions: tuple[str, ...] = Field(min_length=1)
    role_families: RoleFamilies


class Objectives(EditableObjectives):
    """La forma entera de `config/objectives.yaml`, las seis claves.

    Valida el documento completo tras aplicar una edición -toda su forma,
    no solo lo que el resto de la aplicación lee hoy de este fichero
    (`role_families.core`)-, porque este es el único momento en que algo
    comprueba que el fichero entero sigue teniendo sentido.
    """

    version: int = Field(ge=1)
    # YAML sin comillas lo lee como fecha, no como texto: `ruamel` lo carga
    # como `datetime.date` y hay que fecharlo de vuelta con lo mismo, no con
    # un string, para que se escriba sin comillas igual que estaba.
    updated_at: date


# ---------------------------------------------------------------------------
# `config/preferences.yaml` -- Fase 2 M1
#
# Ninguna de sus nueve claves es vocabulario de código: a diferencia de
# `role_families`, nada de este fichero se compara contra un enum en ningún
# sitio de `services/api/src` (comprobado por grep antes de escribir este
# módulo). Todo es texto y número libres, así que no hay ninguna puerta de
# vocabulario que añadir aquí, a diferencia de `RoleFamilies` arriba.
# ---------------------------------------------------------------------------


class WorkContent(BaseModel):
    preference: str = Field(min_length=1)
    avoid_narrow_specialization: bool
    client_facing: str = Field(min_length=1)
    programming: str = Field(min_length=1)
    travel: str = Field(min_length=1)


class WorkIntensity(BaseModel):
    willing_to_accept_high_intensity: bool
    intended_duration_years: tuple[int, int]
    condition: str = Field(min_length=1)

    @model_validator(mode="after")
    def _rango_creciente(self) -> WorkIntensity:
        low, high = self.intended_duration_years
        if low > high:
            raise ValueError(
                "intended_duration_years debe ir de menor a mayor: "
                f"[{low}, {high}] no lo es"
            )
        return self


class WorkMode(BaseModel):
    onsite: str = Field(min_length=1)
    hybrid: str = Field(min_length=1)
    remote: str = Field(min_length=1)


class Geography(BaseModel):
    eu_passport: bool
    visa_sponsorship: str = Field(min_length=1)
    countries: str = Field(min_length=1)
    madrid_advantage: str = Field(min_length=1)


class Compensation(BaseModel):
    spain_minimum_gross_eur: int = Field(ge=0)
    current_madrid_gross_eur: int = Field(ge=0)
    current_madrid_net_monthly_eur: int = Field(ge=0)
    current_madrid_payments_per_year: int = Field(ge=1)
    current_living_costs_monthly_eur: tuple[int, int]
    current_annual_savings_eur: int = Field(ge=0)
    savings_baseline_note: str = Field(min_length=1)
    abroad_housing_assumption: str = Field(min_length=1)
    outside_madrid_rule: str = Field(min_length=1)
    international_targets: str = Field(min_length=1)

    @model_validator(mode="after")
    def _rango_creciente(self) -> Compensation:
        low, high = self.current_living_costs_monthly_eur
        if low > high:
            raise ValueError(
                "current_living_costs_monthly_eur debe ir de menor a mayor: "
                f"[{low}, {high}] no lo es"
            )
        return self


class Language(BaseModel):
    spanish: str = Field(min_length=1)
    english_interview: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()
    cv_policy: str = Field(min_length=1)


class ProfessionalProjectDocumentation(BaseModel):
    contribution_granularity: str = Field(min_length=1)
    avoid_internal_task_breakdown: bool
    acceptable_evidence: str = Field(min_length=1)
    cv_implication: str = Field(min_length=1)


class EditablePreferences(BaseModel):
    work_content: WorkContent
    work_intensity: WorkIntensity
    work_mode: WorkMode
    geography: Geography
    compensation: Compensation
    language: Language
    professional_project_documentation: ProfessionalProjectDocumentation


class Preferences(EditablePreferences):
    """La forma entera de `config/preferences.yaml`, las nueve claves."""

    version: int = Field(ge=1)
    updated_at: date


# ---------------------------------------------------------------------------
# `config/constraints.yaml` -- Fase 2 M1
# ---------------------------------------------------------------------------


class CurrentKnownConstraints(BaseModel):
    timing: str = Field(min_length=1)
    spain_salary_floor_gross_eur: int = Field(ge=0)
    relocation: str = Field(min_length=1)
    visa_sponsorship: str = Field(min_length=1)
    eu_work_authorization: bool


class SectorPolicy(BaseModel):
    excluded_industries: tuple[str, ...] = ()
    rule: str = Field(min_length=1)
    note: str = Field(min_length=1)


class DisqualifyingConditionEdit(BaseModel):
    """Una fila de `disqualifying_conditions`. Solo `id` y `rule`: son los
    dos únicos campos que `data_repo/loader.py` lee del lado de solo
    lectura -el resto (`evaluable_from_posting`/`affects`, distinto por
    fila) no lo consume ningún código, así que se enseña de solo lectura
    junto a cada fila y no se toca desde aquí.

    A diferencia de `role_families`, `id` no es vocabulario de código: no
    se compara contra ningún enum en ningún sitio, solo viaja como texto
    libre hasta el prompt del modelo (`assessment/prompt.py`). Alcance de
    esta rebanada: añadir filas y editar su `rule`, sin borrar ni
    reordenar -confirmado con Pablo el 2026-09-07-.
    """

    id: str = Field(min_length=1)
    rule: str = Field(min_length=1)


class AcceptedConditions(BaseModel):
    on_call_and_shift_work: str = Field(min_length=1)
    high_intensity: str = Field(min_length=1)


class SupersededDecisionEdit(BaseModel):
    """Una entrada de `superseded_decisions`, que en el YAML es un mapa de
    clave -> texto y no una lista: aquí se transporta como lista ordenada
    de pares para que el formulario pueda añadir, editar y borrar entradas
    con CRUD completo -decidido con Pablo el 2026-09-07-, y `constraints.py`
    la reconstruye como mapa al escribir."""

    key: str = Field(min_length=1)
    text: str = Field(min_length=1)


class EditableConstraints(BaseModel):
    # Editable, a diferencia de `fixed_sections` en `cv_variants.yaml`:
    # decidido con Pablo el 2026-09-07 confiar en que sabe lo que hace al
    # tocar sus propias líneas rojas éticas. `min_length=1` solo protege
    # contra vaciar la lista entera por accidente, no restringe qué se
    # puede escribir en ella.
    hard_constraints: tuple[str, ...] = Field(min_length=1)
    current_known_constraints: CurrentKnownConstraints
    sector_policy: SectorPolicy
    disqualifying_conditions: tuple[DisqualifyingConditionEdit, ...] = Field(
        min_length=1
    )
    accepted_conditions: AcceptedConditions
    pending_decisions: tuple[str, ...] = ()
    superseded_decisions: tuple[SupersededDecisionEdit, ...] = ()

    @field_validator("superseded_decisions", mode="before")
    @classmethod
    def _superseded_decisions_desde_el_mapa_del_yaml(cls, value: Any) -> Any:
        """El YAML real declara `superseded_decisions` como un mapa de
        clave -> texto, no como lista -a diferencia de lo que asumía el
        troceo original de esta rebanada-. `current()` valida el
        documento tal cual sale de `ruamel` (un `CommentedMap`), y el
        formulario edita y manda la lista de pares que sí es
        `SupersededDecisionEdit`; aquí se acepta la primera forma y se
        convierte a la segunda, preservando el orden de inserción."""
        if isinstance(value, Mapping):
            return [{"key": key, "text": text} for key, text in value.items()]
        return value

    @model_validator(mode="after")
    def _condiciones_sin_id_repetido(self) -> EditableConstraints:
        ids = [condition.id for condition in self.disqualifying_conditions]
        duplicated = sorted({cid for cid in ids if ids.count(cid) > 1})
        if duplicated:
            raise ValueError(f"disqualifying_conditions repite id {duplicated}")
        return self

    @model_validator(mode="after")
    def _decisiones_sustituidas_sin_clave_repetida(self) -> EditableConstraints:
        keys = [decision.key for decision in self.superseded_decisions]
        duplicated = sorted({key for key in keys if keys.count(key) > 1})
        if duplicated:
            raise ValueError(f"superseded_decisions repite clave {duplicated}")
        return self


class Constraints(EditableConstraints):
    """La forma entera de `config/constraints.yaml`, las nueve claves."""

    version: int = Field(ge=1)
    updated_at: date


# ---------------------------------------------------------------------------
# `config/cv_variants.yaml` -- Fase 2 M2, de solo lectura
#
# No se edita en M2 (eso es M3): se lee del propio clon de escritura, ya
# sincronizado por `pull --rebase`, para validar las `claim_rules` contra
# el texto de un bullet al guardarlo. Modelo mínimo -solo el bloque que
# hace falta para esa validación, no el fichero entero-.
# ---------------------------------------------------------------------------


class ProfessionalContributionLanguage(BaseModel):
    allowed: tuple[str, ...] = Field(min_length=1)
    blocked_without_specific_confirmation: tuple[str, ...] = ()


class ClaimRulesForValidation(BaseModel):
    professional_contribution_language: ProfessionalContributionLanguage


# ---------------------------------------------------------------------------
# `cv/content/professional_bullet_bank.yaml` -- Fase 2 M2
#
# Cada bullet trae más campos de los que el formulario edita. Alcance
# confirmado con Pablo el 2026-09-07: solo `text_en`, `evidence_status` y
# `cv_usage` son editables; `bullet_id` es la identidad (inmutable tras
# crearse, casado igual que `disqualifying_conditions.id` en M1) y el resto
# -`bullet_type`, `project_id`, `angle`, `confidentiality_status`,
# `role_variants`, `blocked_by`, `guardrail`- pasa intacto, sin
# reconstruirse. `policy` (verbos, autorizaciones fechadas, la revisión de
# redacción de estado del 2026-08-14) es un bloque fijo: se lee y se
# reescribe tal cual, nunca lo reconstruye Python.
# ---------------------------------------------------------------------------


class BulletEdit(BaseModel):
    bullet_id: str = Field(min_length=1)
    text_en: str = Field(min_length=1)
    evidence_status: BulletEvidenceStatus
    cv_usage: BulletCvUsage


class EditableBulletBank(BaseModel):
    bullets: tuple[BulletEdit, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _sin_bullet_id_repetido(self) -> EditableBulletBank:
        ids = [bullet.bullet_id for bullet in self.bullets]
        duplicated = sorted({bid for bid in ids if ids.count(bid) > 1})
        if duplicated:
            raise ValueError(f"bullets repite bullet_id {duplicated}")
        return self


class Bullet(BaseModel):
    """Una fila entera de `bullets`, tal como sale de `ruamel` al leer."""

    bullet_id: str = Field(min_length=1)
    bullet_type: str = Field(min_length=1)
    project_id: str | None = None
    angle: str = Field(min_length=1)
    text_en: str = Field(min_length=1)
    evidence_status: BulletEvidenceStatus
    confidentiality_status: str | None = None
    cv_usage: BulletCvUsage
    role_variants: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    guardrail: str | None = None


class BulletBank(BaseModel):
    """La forma entera de `professional_bullet_bank.yaml`."""

    version: int = Field(ge=1)
    updated_at: date
    language: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    # Bloque fijo, sin editar: se transporta tal cual para poder enseñarlo
    # (la revisión de redacción de estado, entre otros) sin darle forma.
    policy: dict[str, Any]
    bullets: tuple[Bullet, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _sin_bullet_id_repetido(self) -> BulletBank:
        ids = [bullet.bullet_id for bullet in self.bullets]
        duplicated = sorted({bid for bid in ids if ids.count(bid) > 1})
        if duplicated:
            raise ValueError(
                f"bullets repite bullet_id {duplicated}; una referencia desde "
                "candidate_bullet_priority dejaría de ser inequívoca"
            )
        return self


# ---------------------------------------------------------------------------
# `cv/content/role_variant_content.yaml` -- Fase 2 M2
#
# Las 5 claves de `variants` son fijas -coinciden con `base_variants` de
# `config/cv_variants.yaml`, que es M3-: decidido con Pablo el 2026-09-07
# no ofrecer alta ni baja de variantes aquí, solo editar su contenido. La
# comprobación de que el envío declara exactamente esas claves vive en
# `role_variant_content.py`, no en este modelo: el modelo no conoce el
# fichero vigente.
# ---------------------------------------------------------------------------


class SkillRowEdit(BaseModel):
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class VariantContent(BaseModel):
    """El contenido de una variante. Sin distinción editable/completo: a
    diferencia de `Bullet`, ninguna variante trae metadato que el
    formulario no gestione."""

    display_name: str = Field(min_length=1)
    use_when: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    skills: tuple[SkillRowEdit, ...] = Field(min_length=1)


class EditableRoleVariantContent(BaseModel):
    variants: dict[str, VariantContent] = Field(min_length=1)


class RoleVariantContent(EditableRoleVariantContent):
    """La forma entera de `role_variant_content.yaml`."""

    version: int = Field(ge=1)
    updated_at: date
    language: str = Field(min_length=1)
    skills_confirmation: str = Field(min_length=1)
