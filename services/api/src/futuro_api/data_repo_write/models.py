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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from futuro_api.data_repo.vocabularies import EffortTier
from futuro_api.data_repo_write.vocabularies import (
    BulletCvUsage,
    BulletEvidenceStatus,
    ProjectCvUsage,
)
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


# ---------------------------------------------------------------------------
# `config/cv_variants.yaml` -- Fase 2 M3
#
# `claim_rules`, `fixed_sections`, `tailorable_sections`,
# `vacancy_tailoring_process` y `strategy` son de solo lectura, sin ningún
# camino de edición: `fixed_sections` por regla dura de `AGENTS.md`,
# `claim_rules` porque M2 ya depende de él como barrera externa que valida
# cada bullet al guardarlo -decidido con Pablo el 2026-09-07 no ofrecerle
# aquí el mismo criterio permisivo que sí se le dio a `hard_constraints`
# en M1-. Se leen y se reescriben tal cual, mismo tratamiento que `policy`
# en `BulletBank`.
#
# `base_variants` tiene 6 claves reales, solo 5 son editables:
# `quant_exploratory` -detectada por traer `status`, no por su nombre, para
# que la regla generalice si se bloquea otra variante igual el día de
# mañana- no tiene las listas de prioridad y no tiene contraparte en
# `role_variant_content.yaml`. Decidido con Pablo el 2026-09-07: de solo
# lectura, fuera del formulario y fuera de la validación cruzada. Las 5
# activas comparten un núcleo editable -`target_roles`/`emphasis`/
# `professional_project_priority`/`public_project_priority`/
# `candidate_bullet_priority`-; sus campos atípicos (`display_name`,
# `target_role_condition`, `note`, `exclusive_evidence`) son de solo
# lectura, mismo patrón que los campos no gestionados de `Bullet` en M2.
# ---------------------------------------------------------------------------


class BaseVariantEdit(BaseModel):
    """Los campos editables, comunes a las 5 variantes activas."""

    target_roles: tuple[str, ...] = Field(min_length=1)
    emphasis: tuple[str, ...] = Field(min_length=1)
    professional_project_priority: tuple[str, ...] = Field(min_length=1)
    public_project_priority: tuple[str, ...] = Field(min_length=1)
    candidate_bullet_priority: tuple[str, ...] = Field(min_length=1)


class EditableCvVariants(BaseModel):
    base_variants: dict[str, BaseVariantEdit] = Field(min_length=1)


class BaseVariant(BaseModel):
    """Una fila entera de `base_variants`, tal como sale de `ruamel` al
    leer. Una variante activa siempre trae el núcleo de `BaseVariantEdit`
    más, según el caso, alguno de los campos atípicos; `status` marca la
    excepción -`quant_exploratory` hoy-, donde el resto puede faltar de
    verdad."""

    target_roles: tuple[str, ...] = ()
    emphasis: tuple[str, ...] = ()
    professional_project_priority: tuple[str, ...] = ()
    public_project_priority: tuple[str, ...] = ()
    candidate_bullet_priority: tuple[str, ...] = ()
    display_name: str | None = None
    target_role_condition: str | None = None
    note: str | None = None
    exclusive_evidence: tuple[str, ...] = ()
    status: str | None = None


class CvVariants(BaseModel):
    """La forma entera de `config/cv_variants.yaml`."""

    version: int = Field(ge=1)
    updated_at: date
    strategy: str = Field(min_length=1)
    # Bloques fijos, sin editar por ningún camino: se transportan tal cual.
    claim_rules: dict[str, Any]
    tailorable_sections: tuple[str, ...] = ()
    fixed_sections: tuple[str, ...] = ()
    base_variants: dict[str, BaseVariant] = Field(min_length=1)
    vacancy_tailoring_process: tuple[str, ...] = ()

    @property
    def active_variant_ids(self) -> frozenset[str]:
        """Las claves con las listas de prioridad -todo `base_variants`
        salvo las bloqueadas con `status`, `quant_exploratory` hoy-."""
        return frozenset(
            variant_id
            for variant_id, variant in self.base_variants.items()
            if variant.status is None
        )

    @property
    def referenced_bullet_ids(self) -> frozenset[str]:
        """Todo `bullet_id` referenciado desde una variante activa, en
        `candidate_bullet_priority` o en `exclusive_evidence` -esta
        segunda no se edita en esta rebanada, pero se revalida igual,
        misma disciplina de "revalidar el documento entero" que ya
        aplican los cuatro módulos anteriores."""
        ids: set[str] = set()
        for variant_id in self.active_variant_ids:
            variant = self.base_variants[variant_id]
            ids.update(variant.candidate_bullet_priority)
            ids.update(variant.exclusive_evidence)
        return frozenset(ids)

    @property
    def referenced_project_ids(self) -> frozenset[str]:
        """Todo `project_id` referenciado desde una variante activa, en
        `professional_project_priority` o en `public_project_priority`."""
        ids: set[str] = set()
        for variant_id in self.active_variant_ids:
            variant = self.base_variants[variant_id]
            ids.update(variant.professional_project_priority)
            ids.update(variant.public_project_priority)
        return frozenset(ids)


# ---------------------------------------------------------------------------
# `profile/project_catalog.yaml` -- Fase 2 M3
#
# Primer módulo de escritura para este fichero: sin ningún camino de
# lectura previo en la aplicación, confirmado por grep el 2026-09-07.
# Mismo mecanismo que los demás: `current`/`prepare`/`write`, revalida el
# documento entero tras aplicar la edición.
#
# `project_id` casa cada edición, igual que `bullet_id` en M2. Sin alta ni
# baja: `discovery_backlog` -candidatos sin auditar- y promover uno de
# ellos a proyecto quedan fuera, es una decisión mayor con su propio
# dossier detrás, no algo que ofrezca este formulario.
#
# Editable por fila: `safe_name`, `evidence_status`, `cv_usage`,
# `interview_usage`, `pending_confirmations`. `source_type`,
# `confidentiality`, `canonical_source`, `role_family_fit` y
# `professional_value_signals` son de solo lectura -estructurales, sin
# motivo para tocarlos desde aquí-.
#
# `evidence_status` reutiliza `BulletEvidenceStatus` -mismos cuatro
# valores, y es precisamente el fichero del que M2 los tomó-.
# `cv_usage`/`interview_usage` usan `ProjectCvUsage`, un vocabulario
# propio y distinto de `BulletCvUsage` aunque comparta nombre de campo.
# ---------------------------------------------------------------------------


class ProjectEdit(BaseModel):
    project_id: str = Field(min_length=1)
    safe_name: str = Field(min_length=1)
    evidence_status: BulletEvidenceStatus
    cv_usage: ProjectCvUsage
    interview_usage: ProjectCvUsage
    pending_confirmations: tuple[str, ...] = ()


class EditableProjectCatalog(BaseModel):
    projects: tuple[ProjectEdit, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _sin_project_id_repetido(self) -> EditableProjectCatalog:
        ids = [project.project_id for project in self.projects]
        duplicated = sorted({pid for pid in ids if ids.count(pid) > 1})
        if duplicated:
            raise ValueError(f"projects repite project_id {duplicated}")
        return self


class Project(BaseModel):
    """Una fila entera de `projects`, tal como sale de `ruamel` al leer."""

    project_id: str = Field(min_length=1)
    safe_name: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    evidence_status: BulletEvidenceStatus
    confidentiality: str = Field(min_length=1)
    canonical_source: str = Field(min_length=1)
    role_family_fit: tuple[str, ...] = ()
    professional_value_signals: tuple[str, ...] = ()
    cv_usage: ProjectCvUsage
    interview_usage: ProjectCvUsage
    pending_confirmations: tuple[str, ...] = ()


class ProjectCatalog(BaseModel):
    """La forma entera de `profile/project_catalog.yaml`."""

    model_config = ConfigDict(populate_by_name=True)

    version: int = Field(ge=1)
    updated_at: date
    purpose: str = Field(min_length=1)
    # Bloques fijos, sin editar: se transportan tal cual. `schema` es
    # nombre reservado por `BaseModel` en Pydantic v2 (solo un aviso, no un
    # error, pero uno evitable): se alía al nombre real del campo en el
    # YAML y se acepta también por su nombre de atributo Python.
    rules: dict[str, Any]
    catalog_schema: dict[str, Any] = Field(alias="schema")
    projects: tuple[Project, ...] = Field(min_length=1)
    discovery_backlog: dict[str, Any]

    @model_validator(mode="after")
    def _sin_project_id_repetido(self) -> ProjectCatalog:
        ids = [project.project_id for project in self.projects]
        duplicated = sorted({pid for pid in ids if ids.count(pid) > 1})
        if duplicated:
            raise ValueError(
                f"projects repite project_id {duplicated}; una referencia "
                "desde professional_project_priority/public_project_priority "
                "dejaría de ser inequívoca"
            )
        return self

    @property
    def project_id_set(self) -> frozenset[str]:
        return frozenset(project.project_id for project in self.projects)


# ---------------------------------------------------------------------------
# `config/scoring_model.yaml` -- Fase 2 M4, la última rebanada de Fase 2
#
# Sin validación cruzada con otros ficheros: a diferencia de M3, ninguna
# referencia de este fichero a otro (`role_fit.note` menciona "familias de
# objectives.yaml" y "banco de bullets" en prosa) es un identificador que
# el código resuelva.
#
# **Solo lectura, decidido con Pablo el 2026-09-08, mismo criterio que
# `claim_rules`/`fixed_sections` en M3**: `version` y `status` -ninguno de
# los dos lo lee ningún código, y auto-incrementar `version` en cada
# guardado lo degradaría de hito con nombre (3 bumps reales en un mes,
# cada uno atado a un cierre concreto) a ruido-; el nombre del bloque
# `baseline_*` -renombrar la ciudad de referencia es un evento raro con
# implicaciones en las anclas económicas, no una edición de formulario-;
# `scale` -atada al CHECK de `offer_assessment_dimensions`, exige
# migración-; y el bloque entero de `portfolio_assignment` +
# `output.effort_tier.{tier}.when/do` + `.note` +
# `missing_data.rule/method/coverage/below_minimum` +
# `output.required_fields`. Este último grupo documenta en prosa umbrales
# que en realidad decide a mano `assessment/scoring.py`
# (`VALUE_FLOOR`/`VALUE_FULL_EFFORT`/`BUCKET_OF_BAND`, el orden de
# `_portfolio_bucket`): abrirlo a edición no cambiaría ni una coma de cómo
# se puntúa una oferta, y ya hay un caso real de esa prosa mintiendo sobre
# su propio estado -la nota de `cheap` seguía diciendo "pendiente de
# implementar en futuro-app" el 2026-09-07, dos días después de que
# `scoring.py` ya lo implementara-.
#
# **La excepción dentro de ese último grupo es
# `output.effort_tier.evaluation_order`**: a diferencia de sus vecinos,
# `assessment/scoring.py._effort_tier` sí lo recorre de verdad (`for tier
# in model.effort_evaluation_order`), así que reordenarlo cambia el
# resultado real. Se edita como reordenación pura del vocabulario cerrado
# de `EffortTier` -mismas cuatro etiquetas que ya exige
# `data_repo/loader.py`-, sin alta ni baja.
#
# **Editable sin puerta de vocabulario** -confirmado por grep el
# 2026-09-08: ningún código ramifica sobre el nombre de una dimensión o de
# un filtro, y Fase 1 M2 ya renombró una dimensión
# (`expected_net_savings` -> `gross_compensation_vs_baseline`) sin tocar
# ninguna línea de código-: `weights`/`anchors` (alta, baja y renombrado
# de dimensión) y `gates` (alta, baja y renombrado de filtro). `baseline`
# (los campos dentro del bloque, no su nombre), `description`,
# `portfolio_policy` y `notes` tampoco tienen vocabulario que proteger.
#
# **Editable con puerta de vocabulario en las claves**:
# `probability_bands` -las cuatro claves fijas contra `ProbabilityBand`,
# que `data_repo/loader.py` exige que el YAML declare exactamente; el
# texto de cada banda, que llega al modelo por el prompt, es libre- y
# `output.effort_tier.evaluation_order` -permutación exacta de las cuatro
# etiquetas de `EffortTier`, mismo cierre-.
# ---------------------------------------------------------------------------


class BaselineEdit(BaseModel):
    """Los campos de `baseline_<ciudad>`, editables. El nombre del bloque
    y su propio `updated_at` quedan fuera: el primero por ser un evento
    raro y no una edición de formulario, el segundo porque se estampa
    solo con la fecha de la escritura, igual que el del documento."""

    gross_annual_eur: int = Field(ge=0)
    payments_per_year: int = Field(ge=1)
    net_monthly_eur: int = Field(ge=0)
    net_annual_eur: int = Field(ge=0)
    living_costs_monthly_eur: tuple[int, int]
    annual_savings_eur: tuple[int, int]
    reference_savings_eur: int = Field(ge=0)
    savings_rate: float = Field(ge=0, le=1)
    cause: str = Field(min_length=1)
    implication: str = Field(min_length=1)

    @model_validator(mode="after")
    def _rangos_crecientes(self) -> BaselineEdit:
        for field_name, pair in (
            ("living_costs_monthly_eur", self.living_costs_monthly_eur),
            ("annual_savings_eur", self.annual_savings_eur),
        ):
            if pair[0] > pair[1]:
                raise ValueError(
                    f"{field_name} debe ir de menor a mayor: {list(pair)} no lo es"
                )
        return self


class LabeledTextRow(BaseModel):
    """Una fila «etiqueta -> texto» de longitud variable. La reutilizan
    las anclas de una dimensión (niveles numéricos `0`/`1`/`3`/`5` más
    notas libres como `assumption`/`includes`/`measured_against`) y los
    filtros (`pass`/`fail`/`stretch`/`pending`/`pass_spain`/`pass_abroad`/
    ..., más `context`/`note`) -mismo criterio que `SkillRowEdit` en
    `role_variant_content.yaml`: sin clave estable que casar entre
    escrituras, así que cada guardado sustituye el juego entero de
    etiquetas."""

    label: str = Field(min_length=1)
    text: str = Field(min_length=1)


def is_anchor_level(label: str) -> bool:
    """Si `label` es un nivel numérico de ancla (`"0"`, `"1"`, ...) o una
    nota libre (`"assumption"`, ...) -mismo criterio que `_dimensions` en
    `data_repo/loader.py`-. Público porque `scoring_model.py` lo reutiliza
    al aplicar una edición."""
    try:
        int(label)
    except ValueError:
        return False
    return True


_GATE_NOTE_LABELS = frozenset({"context", "note"})


class DimensionEdit(BaseModel):
    """Una dimensión de `weights`/`anchors`. Alta, baja y renombrado
    libres -ver el bloque de comentarios de arriba-. Al menos una fila de
    `anchors` tiene que traer una etiqueta numérica: `data_repo/loader.py`
    exige al menos un ancla o el modelo de scoring no tiene contra qué
    puntuar."""

    name: str = Field(min_length=1)
    weight: int = Field(gt=0)
    anchors: tuple[LabeledTextRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _anclas_sin_etiqueta_repetida_y_con_algun_nivel(self) -> DimensionEdit:
        labels = [row.label for row in self.anchors]
        duplicated = sorted({label for label in labels if labels.count(label) > 1})
        if duplicated:
            raise ValueError(
                f"«{self.name}»: repite la etiqueta {duplicated} entre sus anclas"
            )
        if not any(is_anchor_level(label) for label in labels):
            raise ValueError(
                f"«{self.name}»: no declara ningún nivel numérico (0/1/3/5); "
                "sin eso el modelo de scoring no tiene contra qué puntuar"
            )
        return self


class GateEdit(BaseModel):
    """Un filtro eliminatorio de `gates`. Alta, baja y renombrado libres
    -ver el bloque de comentarios de arriba-. Al menos una fila tiene que
    ser un criterio, no `context`/`note`: sin ningún criterio el filtro no
    dice cuándo se pasa ni cuándo se falla."""

    name: str = Field(min_length=1)
    rows: tuple[LabeledTextRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _filas_sin_etiqueta_repetida_y_con_algun_criterio(self) -> GateEdit:
        labels = [row.label for row in self.rows]
        duplicated = sorted({label for label in labels if labels.count(label) > 1})
        if duplicated:
            raise ValueError(
                f"«{self.name}»: repite la etiqueta {duplicated} entre sus filas"
            )
        if not any(label not in _GATE_NOTE_LABELS for label in labels):
            raise ValueError(
                f"«{self.name}»: no declara ningún criterio -todo es "
                "«context»/«note»-; sin eso el filtro no dice cuándo se pasa "
                "ni cuándo se falla"
            )
        return self


class ProbabilityBandsEdit(BaseModel):
    """Las cuatro bandas de `probability_bands`. Vocabulario de código
    -`ProbabilityBand`, en `data_repo/vocabularies.py`-: la aplicación
    ramifica sobre estos cuatro nombres exactos para calcular el cubo de
    cartera, así que las claves son fijas y solo el texto de cada banda
    -que llega al modelo por `assessment/prompt.py`- es editable."""

    high: str = Field(min_length=1)
    medium: str = Field(min_length=1)
    low: str = Field(min_length=1)
    very_low: str = Field(min_length=1)


class PortfolioPolicyEdit(BaseModel):
    """`portfolio_policy`: el reparto de referencia de la cartera. Ningún
    código lo lee -confirmado por grep el 2026-09-08: ni
    `data_repo/loader.py` ni `assessment/scoring.py` lo tocan, a
    diferencia de `portfolio_assignment`, con el que no hay que
    confundirlo-, así que es descriptivo y totalmente editable, mismo
    trato que `hard_constraints`."""

    realistic: float = Field(ge=0, le=1)
    realistic_stretch: float = Field(ge=0, le=1)
    aspirational: float = Field(ge=0, le=1)
    experimental: float = Field(ge=0, le=1)
    status: str = Field(min_length=1)
    note: str = Field(min_length=1)


class EditableScoringModel(BaseModel):
    """Lo que el formulario de M4 edita. Ver el bloque de comentarios de
    arriba para qué queda fuera y por qué."""

    description: str = Field(min_length=1)
    baseline: BaselineEdit
    dimensions: tuple[DimensionEdit, ...] = Field(min_length=1)
    gates: tuple[GateEdit, ...] = Field(min_length=1)
    probability_bands: ProbabilityBandsEdit
    minimum_coverage: float = Field(gt=0, le=1)
    never_rule: str = Field(min_length=1)
    effort_evaluation_order: tuple[EffortTier, ...]
    portfolio_policy: PortfolioPolicyEdit
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _dimensiones_sin_nombre_repetido(self) -> EditableScoringModel:
        names = [dimension.name for dimension in self.dimensions]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            raise ValueError(f"dimensions repite el nombre {duplicated}")
        return self

    @model_validator(mode="after")
    def _filtros_sin_nombre_repetido(self) -> EditableScoringModel:
        names = [gate.name for gate in self.gates]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            raise ValueError(f"gates repite el nombre {duplicated}")
        return self

    @model_validator(mode="after")
    def _orden_de_esfuerzo_es_permutacion_completa(self) -> EditableScoringModel:
        declared = frozenset(self.effort_evaluation_order)
        if declared != frozenset(EffortTier) or len(
            self.effort_evaluation_order
        ) != len(EffortTier):
            raise ValueError(
                "effort_evaluation_order debe declarar cada nivel de "
                f"{sorted(tier.value for tier in EffortTier)} exactamente una "
                f"vez, y es {[tier.value for tier in self.effort_evaluation_order]}"
            )
        return self


class ScoringModel(EditableScoringModel):
    """La forma entera de `config/scoring_model.yaml`, las 15 claves.

    Los bloques de solo lectura viajan como `dict[str, Any]` tal cual
    -mismo tratamiento que `claim_rules` en `CvVariants`-: no los
    reconstruye Python nunca, así que no hace falta tipar su interior para
    que la disciplina de "revalidar el documento entero" los cubra."""

    version: int = Field(ge=1)
    status: str = Field(min_length=1)
    updated_at: date
    baseline_name: str = Field(min_length=1)
    scale: dict[str, Any]
    portfolio_assignment: dict[str, Any]
    missing_data: dict[str, Any]
    output: dict[str, Any]
