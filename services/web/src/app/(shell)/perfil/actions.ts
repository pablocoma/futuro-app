"use server";

import {
  commitBulletBank,
  commitConstraints,
  commitCvVariants,
  commitObjectives,
  commitPreferences,
  commitProjectCatalog,
  commitRoleVariants,
  diffBulletBank,
  diffConstraints,
  diffCvVariants,
  diffObjectives,
  diffPreferences,
  diffProjectCatalog,
  diffRoleVariants,
  type BaseVariantEdit,
  type BulletEdit,
  type DisqualifyingCondition,
  type EditableBulletBank,
  type EditableConstraints,
  type EditableCvVariants,
  type EditableObjectives,
  type EditablePreferences,
  type EditableProjectCatalog,
  type EditableRoleVariantContent,
  type ProjectEdit,
  type SupersededDecision,
  type VariantContent,
} from "@/lib/api";
import { DECLARABLE_ROLE_FAMILIES } from "@/lib/labels";

// Solo el tipo, no un valor: un fichero "use server" únicamente puede
// exportar funciones async. `INITIAL_OBJECTIVES_STATE` vive en
// `ObjectivesForm.tsx`, que es quien lo necesita.
export type ObjectivesFormState = {
  error: string | null;
  diff: string | null;
  saved: boolean;
  commitSha: string | null;
};

export type PreferencesFormState = ObjectivesFormState;
export type ConstraintsFormState = ObjectivesFormState;
export type BulletBankFormState = ObjectivesFormState;
export type RoleVariantsFormState = ObjectivesFormState;
export type CvVariantsFormState = ObjectivesFormState;
export type ProjectCatalogFormState = ObjectivesFormState;

/** Texto separado por comas -> lista sin vacíos, mismo criterio en todos
 * los campos de este tipo (`success_dimensions`, `evidence`,
 * `excluded_industries`, `pending_decisions`, `hard_constraints`). */
function commaList(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

/**
 * Una familia por `<fieldset>`, con tres radios -ninguna / core /
 * exploratoria-: es lo que hace imposible que el formulario mande una
 * familia repetida entre las dos listas, en vez de dejar que el 422 de la
 * API lo diga después de escribir texto libre.
 */
function parseEdit(formData: FormData): EditableObjectives {
  const core: string[] = [];
  const exploratory: string[] = [];
  for (const family of DECLARABLE_ROLE_FAMILIES) {
    const choice = formData.get(`family_${family}`);
    if (choice === "core") core.push(family);
    if (choice === "exploratory") exploratory.push(family);
  }

  const successDimensions = commaList(formData.get("success_dimensions"));

  return {
    transition: {
      target_year: Number(formData.get("target_year")),
      urgency: String(formData.get("urgency") ?? "").trim(),
      expected_tenure_years: [
        Number(formData.get("tenure_min")),
        Number(formData.get("tenure_max")),
      ],
    },
    primary_objective: {
      statement: String(formData.get("statement") ?? "").trim(),
    },
    success_dimensions: successDimensions,
    role_families: { core, exploratory },
  };
}

/**
 * Un único action para las dos mitades del mecanismo: qué botón se ha
 * pulsado decide si se calcula el diff o si se commitea y empuja, pero los
 * dos parten del mismo formulario y del mismo `parseEdit`.
 */
export async function reviewObjectives(
  _previous: ObjectivesFormState,
  formData: FormData,
): Promise<ObjectivesFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parseEdit(formData);

  if (intent === "commit") {
    const result = await commitObjectives(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffObjectives(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}

function parsePreferencesEdit(formData: FormData): EditablePreferences {
  const get = (name: string) => String(formData.get(name) ?? "").trim();
  return {
    work_content: {
      preference: get("preference"),
      avoid_narrow_specialization: formData.get("avoid_narrow_specialization") === "on",
      client_facing: get("client_facing"),
      programming: get("programming"),
      travel: get("travel"),
    },
    work_intensity: {
      willing_to_accept_high_intensity:
        formData.get("willing_to_accept_high_intensity") === "on",
      intended_duration_years: [
        Number(formData.get("duration_min")),
        Number(formData.get("duration_max")),
      ],
      condition: get("condition"),
    },
    work_mode: {
      onsite: get("onsite"),
      hybrid: get("hybrid"),
      remote: get("remote"),
    },
    geography: {
      eu_passport: formData.get("eu_passport") === "on",
      visa_sponsorship: get("visa_sponsorship"),
      countries: get("countries"),
      madrid_advantage: get("madrid_advantage"),
    },
    compensation: {
      spain_minimum_gross_eur: Number(formData.get("spain_minimum_gross_eur")),
      current_madrid_gross_eur: Number(formData.get("current_madrid_gross_eur")),
      current_madrid_net_monthly_eur: Number(
        formData.get("current_madrid_net_monthly_eur"),
      ),
      current_madrid_payments_per_year: Number(
        formData.get("current_madrid_payments_per_year"),
      ),
      current_living_costs_monthly_eur: [
        Number(formData.get("living_costs_min")),
        Number(formData.get("living_costs_max")),
      ],
      current_annual_savings_eur: Number(formData.get("current_annual_savings_eur")),
      savings_baseline_note: get("savings_baseline_note"),
      abroad_housing_assumption: get("abroad_housing_assumption"),
      outside_madrid_rule: get("outside_madrid_rule"),
      international_targets: get("international_targets"),
    },
    language: {
      spanish: get("spanish"),
      english_interview: get("english_interview"),
      evidence: commaList(formData.get("evidence")),
      cv_policy: get("cv_policy"),
    },
    professional_project_documentation: {
      contribution_granularity: get("contribution_granularity"),
      avoid_internal_task_breakdown:
        formData.get("avoid_internal_task_breakdown") === "on",
      acceptable_evidence: get("acceptable_evidence"),
      cv_implication: get("cv_implication"),
    },
  };
}

export async function reviewPreferences(
  _previous: PreferencesFormState,
  formData: FormData,
): Promise<PreferencesFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parsePreferencesEdit(formData);

  if (intent === "commit") {
    const result = await commitPreferences(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffPreferences(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}

/**
 * `disqualifying_conditions` y `superseded_decisions` son filas de largo
 * variable -añadir, en el segundo caso también quitar-, así que viajan
 * como JSON en un campo oculto en vez de nombres de campo indexados:
 * `ConstraintsForm` ya las mantiene como estado de React controlado, y
 * serializarlas es más simple y menos frágil que reconstruir un array de
 * `FormData` con claves `dq_id_0`, `dq_id_1`, etc.
 */
function parseConstraintsEdit(formData: FormData): EditableConstraints {
  const get = (name: string) => String(formData.get(name) ?? "").trim();
  const disqualifyingConditions = JSON.parse(
    String(formData.get("disqualifying_conditions_json") ?? "[]"),
  ) as DisqualifyingCondition[];
  const supersededDecisions = JSON.parse(
    String(formData.get("superseded_decisions_json") ?? "[]"),
  ) as SupersededDecision[];

  return {
    hard_constraints: commaList(formData.get("hard_constraints")),
    current_known_constraints: {
      timing: get("timing"),
      spain_salary_floor_gross_eur: Number(
        formData.get("spain_salary_floor_gross_eur"),
      ),
      relocation: get("relocation"),
      visa_sponsorship: get("ckc_visa_sponsorship"),
      eu_work_authorization: formData.get("eu_work_authorization") === "on",
    },
    sector_policy: {
      excluded_industries: commaList(formData.get("excluded_industries")),
      rule: get("sector_rule"),
      note: get("sector_note"),
    },
    disqualifying_conditions: disqualifyingConditions,
    accepted_conditions: {
      on_call_and_shift_work: get("on_call_and_shift_work"),
      high_intensity: get("high_intensity"),
    },
    pending_decisions: commaList(formData.get("pending_decisions")),
    superseded_decisions: supersededDecisions,
  };
}

export async function reviewConstraints(
  _previous: ConstraintsFormState,
  formData: FormData,
): Promise<ConstraintsFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parseConstraintsEdit(formData);

  if (intent === "commit") {
    const result = await commitConstraints(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffConstraints(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}

/**
 * `bullets` viaja como JSON en un campo oculto -mismo criterio que
 * `disqualifying_conditions_json`-: filas de largo variable, ya
 * mantenidas como estado de React en `BulletBankForm`.
 */
function parseBulletBankEdit(formData: FormData): EditableBulletBank {
  const bullets = JSON.parse(
    String(formData.get("bullets_json") ?? "[]"),
  ) as BulletEdit[];
  return { bullets };
}

export async function reviewBulletBank(
  _previous: BulletBankFormState,
  formData: FormData,
): Promise<BulletBankFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parseBulletBankEdit(formData);

  if (intent === "commit") {
    const result = await commitBulletBank(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffBulletBank(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}

/**
 * Las claves de `variants` son fijas -esta rebanada no da de alta ni de
 * baja variantes-, así que el formulario siempre manda las mismas que
 * recibió; solo su contenido (incluidas las filas de `skills`, también de
 * largo variable) viaja como JSON.
 */
function parseRoleVariantsEdit(formData: FormData): EditableRoleVariantContent {
  const variants = JSON.parse(
    String(formData.get("variants_json") ?? "{}"),
  ) as Record<string, VariantContent>;
  return { variants };
}

export async function reviewRoleVariants(
  _previous: RoleVariantsFormState,
  formData: FormData,
): Promise<RoleVariantsFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parseRoleVariantsEdit(formData);

  if (intent === "commit") {
    const result = await commitRoleVariants(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffRoleVariants(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}

/**
 * `base_variants` viaja como JSON en un campo oculto -mismo criterio que
 * `variants_json`-: un diccionario de variantes activas, ya mantenido como
 * estado de React en `CvVariantsForm`. Las variantes con `status` no
 * viajan: son de solo lectura, fuera de esta edición.
 */
function parseCvVariantsEdit(formData: FormData): EditableCvVariants {
  const base_variants = JSON.parse(
    String(formData.get("base_variants_json") ?? "{}"),
  ) as Record<string, BaseVariantEdit>;
  return { base_variants };
}

export async function reviewCvVariants(
  _previous: CvVariantsFormState,
  formData: FormData,
): Promise<CvVariantsFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parseCvVariantsEdit(formData);

  if (intent === "commit") {
    const result = await commitCvVariants(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffCvVariants(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}

/**
 * `projects` viaja como JSON en un campo oculto -mismo criterio que
 * `bullets_json`-: filas de largo fijo -sin alta ni baja en esta
 * rebanada-, ya mantenidas como estado de React en `ProjectCatalogForm`.
 */
function parseProjectCatalogEdit(formData: FormData): EditableProjectCatalog {
  const projects = JSON.parse(
    String(formData.get("projects_json") ?? "[]"),
  ) as ProjectEdit[];
  return { projects };
}

export async function reviewProjectCatalog(
  _previous: ProjectCatalogFormState,
  formData: FormData,
): Promise<ProjectCatalogFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parseProjectCatalogEdit(formData);

  if (intent === "commit") {
    const result = await commitProjectCatalog(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffProjectCatalog(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}
