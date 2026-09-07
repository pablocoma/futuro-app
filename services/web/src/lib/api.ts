import { cookies } from "next/headers";

/**
 * Base interna para llamar a la API desde el servidor de Next.
 *
 * Desde el navegador las rutas `/api/*` las resuelve Caddy en el mismo
 * dominio, así que no hace falta base ninguna. Desde un Server Component,
 * en cambio, la petición sale del contenedor `web` y tiene que ir al
 * servicio `api` por la red de Compose.
 */
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";

export type Health = {
  status: "ok" | "degraded";
  env: string;
  version: string;
  database: "ok" | "unreachable";
  queue: "ok" | "unreachable";
  /**
   * El repositorio privado de donde sale el modelo de scoring. Se informa
   * aparte y no cuenta para el estado general: sin él lo único que no
   * funciona es puntuar.
   */
  data_repo: "ok" | "unreadable" | "not_configured";
  data_repo_error: string | null;
};

export type CurrentUser = {
  email: string;
  via: string;
};

/**
 * Los tres estados de evidencia del contrato de datos. La pantalla los
 * pinta distinto porque significan cosas distintas: un dato publicado trae
 * su cita, uno inferido trae el razonamiento y con cuánta confianza, y uno
 * ausente no trae nada porque nadie ha estimado nada.
 */
export type Evidence = {
  status: "published" | "inferred" | "absent";
  source_quote?: string | null;
  reasoning?: string | null;
  confidence?: "high" | "medium" | "low" | null;
};

export type Field = {
  name: string;
  value: unknown;
  evidence: Evidence;
};

export type Company = {
  id: string | null;
  name: string | null;
  confidence?: "confirmed" | "high" | "medium" | "low" | null;
  evidence: Evidence;
};

export type Requirement = {
  position: number;
  text: string;
  source_quote: string;
  kind: "mandatory" | "desirable" | "anomalous";
  category: string;
  match: "meets" | "partial" | "no_evidence" | null;
  evidence_ref: string | null;
  cv_action: string | null;
};

export type Anomaly = {
  position: number;
  requirement_position: number | null;
  text: string;
  explanation: string;
  source_quote: string;
};

export type Correction = {
  field: string;
  rule: string;
  detail: string;
  previous: string | null;
  applied: string | null;
};

export type Extraction = {
  id: string;
  prompt_version: string;
  model: string;
  extracted_at: string;
  cost_usd: string | null;
  identification: Field[];
  compensation: Field[];
  responsibilities: Field;
  posting_company: Company;
  employer_company: Company;
  requirements: Requirement[];
  anomalies: Anomaly[];
  corrections: Correction[];
};

/**
 * Una barra de la composición ponderada.
 *
 * `weight_share` es el ancho y `score_share` la altura, y los dos vienen
 * calculados de la API. La pantalla no divide pesos: si lo hiciera, habría
 * dos sitios donde se calcula lo mismo y el día que discreparan el dibujo
 * diría una cosa y la puntuación otra.
 *
 * `score` nulo es una dimensión que **no se pudo puntuar**, con su motivo
 * en `unscored_reason`. No es un cero: un cero es una nota.
 */
export type Dimension = {
  dimension: string;
  weight: number;
  weight_share: number;
  score: number | null;
  score_share: number | null;
  citation: string | null;
  reason: string | null;
  anchor: string | null;
  unscored_reason: string | null;
};

/**
 * Un filtro eliminatorio. `pending` es «no se pudo comprobar», que no es
 * «incumple»: el modelo de scoring dice que un filtro que no se puede
 * evaluar nunca se supone superado, y el código no lo supone incumplido.
 */
export type Gate = {
  gate: string;
  status: "pass" | "stretch" | "pending" | "fail";
  citation: string | null;
  reason: string;
};

export type RequirementMatch = {
  requirement_position: number;
  requirement_text: string;
  match: "meets" | "partial" | "no_evidence";
  evidence_ref: string | null;
  reason: string;
};

export type Assessment = {
  id: string;
  assessed_at: string;
  /** `recomputed` es una puntuación recalculada sin llamar al modelo. */
  source: "llm" | "recomputed";
  scoring_model_version: string;
  scoring_model_sha256: string;
  prompt_version: string | null;
  model: string | null;
  cost_usd: string | null;
  /** Nulo cuando la cobertura no llega al mínimo: no se emite puntuación. */
  value_score: string | null;
  coverage: string;
  probability_band: "high" | "medium" | "low" | "very_low";
  probability_reason: string;
  /** Nulo cuando el modelo de scoring no asigna cubo; el motivo lo explica. */
  portfolio_bucket:
    | "realistic"
    | "realistic_stretch"
    | "aspirational"
    | "experimental"
    | "discard"
    | null;
  portfolio_note: string | null;
  effort_tier: "full" | "standard" | "cheap" | "skip";
  dimensions: Dimension[];
  gates: Gate[];
  requirement_matches: RequirementMatch[];
  corrections: Correction[];
};

export type VariantRecommendation = {
  variant: string;
  confidence: "high" | "medium" | "low";
  reason: string;
  recommended_at: string;
  model: string;
  prompt_version: string;
};

export type AssessmentVersion = {
  id: string;
  assessed_at: string;
  source: "llm" | "recomputed";
  scoring_model_version: string;
  value_score: string | null;
};

/**
 * El dossier mínimo: qué variante confirmó Pablo, con qué PDF exacto.
 *
 * `null` en la oferta no es un error, es "todavía no ha decidido". Cambiar
 * de variante crea una fila nueva en la API, así que esto siempre refleja
 * la última.
 */
export type Application = {
  id: string;
  variant: string;
  cv_sha256: string;
  confirmed_at: string;
  recommendation_id: string | null;
};

export type ExtractionStatus =
  | "none"
  | "queued"
  | "running"
  | "succeeded"
  | "failed";

export type Offer = {
  capture: {
    id: string;
    source: string;
    source_url: string | null;
    captured_at: string;
    raw_text: string;
    raw_text_sha256: string;
    deadline: string | null;
    capture_note: string | null;
  };
  extraction_status: ExtractionStatus;
  extraction_error: string | null;
  extraction: Extraction | null;
  versions: { id: string; prompt_version: string; model: string; extracted_at: string }[];
  assessment_status: ExtractionStatus;
  assessment_error: string | null;
  assessment: Assessment | null;
  variant_recommendation: VariantRecommendation | null;
  assessment_versions: AssessmentVersion[];
  application: Application | null;
  /** Vacía si el repositorio de datos no está configurado o no se puede leer. */
  available_variants: string[];
};

export type OfferSummary = {
  id: string;
  captured_at: string;
  title: string | null;
  company: string | null;
  posting_status: string | null;
  extraction_status: ExtractionStatus;
};

export type IngestResult = {
  capture_id: string;
  raw_text_sha256: string;
  duplicate: boolean;
  job_run_id: string | null;
  extraction_status: ExtractionStatus;
  extraction_id: string | null;
};

async function cookieHeaders(): Promise<HeadersInit> {
  const cookieHeader = (await cookies()).toString();
  return cookieHeader ? { cookie: cookieHeader } : {};
}

/**
 * Llama a la API reenviando las cookies de la petición entrante, que es lo
 * que permite que un Server Component vea la misma sesión que el navegador.
 *
 * Devuelve `null` en 401 y en fallo de red: el consumidor distingue "no hay
 * sesión" y "no hay API" por el endpoint que estaba consultando, y ninguna
 * pantalla debe romperse porque la API esté caída.
 */
async function apiGet<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_INTERNAL_URL}${path}`, {
      headers: await cookieHeaders(),
      cache: "no-store",
    });
    if (!response.ok && response.status !== 503) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export type PostResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; detail: string };

/**
 * A diferencia de las lecturas, una escritura que falla no puede devolver
 * `null` y ya está: quien acaba de pegar un anuncio tiene derecho a saber
 * por qué no se ha guardado. Por eso el error viaja con su motivo.
 */
async function apiPost<T>(path: string, body?: unknown): Promise<PostResult<T>> {
  try {
    const response = await fetch(`${API_INTERNAL_URL}${path}`, {
      method: "POST",
      headers: {
        ...(await cookieHeaders()),
        "content-type": "application/json",
      },
      body: JSON.stringify(body ?? {}),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        detail: detailOf(payload) ?? `la API respondió ${response.status}`,
      };
    }
    return { ok: true, data: payload as T };
  } catch {
    return { ok: false, status: 0, detail: "no se ha podido contactar con la API" };
  }
}

/**
 * Saca un mensaje legible de un error de FastAPI, que llega de dos formas:
 * `detail` como cadena en los errores que lanzamos nosotros, y como lista
 * de problemas en los de validación.
 */
function detailOf(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") return null;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: unknown } | undefined;
    if (first && typeof first.msg === "string") return first.msg;
  }
  return null;
}

export function getHealth(): Promise<Health | null> {
  return apiGet<Health>("/api/health");
}

export function getCurrentUser(): Promise<CurrentUser | null> {
  return apiGet<CurrentUser>("/api/auth/me");
}

export function listOffers(): Promise<OfferSummary[] | null> {
  return apiGet<OfferSummary[]>("/api/offers");
}

export function getOffer(id: string): Promise<Offer | null> {
  return apiGet<Offer>(`/api/offers/${id}`);
}

export function ingestOffer(input: {
  raw_text: string;
  capture_note?: string;
  force_reextract?: boolean;
}): Promise<PostResult<IngestResult>> {
  return apiPost<IngestResult>("/api/offers/ingest", input);
}

export function reextractOffer(id: string): Promise<PostResult<IngestResult>> {
  return apiPost<IngestResult>(`/api/offers/${id}/reextract`);
}

export type AssessResult = {
  capture_id: string;
  extraction_id: string;
  job_run_id: string;
  assessment_status: ExtractionStatus;
};

export function assessOffer(id: string): Promise<PostResult<AssessResult>> {
  return apiPost<AssessResult>(`/api/offers/${id}/assess`);
}

export function confirmVariant(
  id: string,
  variant: string,
): Promise<PostResult<Application>> {
  return apiPost<Application>(`/api/offers/${id}/dossier`, { variant });
}

/**
 * `config/objectives.yaml` del repositorio privado, Fase 2 M0.
 *
 * `version` no se edita desde el formulario -no hay ninguna regla de
 * cuándo subirla- y `updated_at` lo estampa el propio backend con la
 * fecha de la escritura, así que los dos viajan de vuelta pero ninguno se
 * manda al editar.
 */
export type Objectives = {
  version: number;
  updated_at: string;
  transition: {
    target_year: number;
    urgency: string;
    expected_tenure_years: [number, number];
  };
  primary_objective: { statement: string };
  success_dimensions: string[];
  role_families: { core: string[]; exploratory: string[] };
};

export type EditableObjectives = Omit<Objectives, "version" | "updated_at">;

export type ObjectivesDiff = { diff: string; validated: Objectives };
export type ObjectivesCommit = { commit_sha: string; diff: string };

/**
 * No reutiliza `apiGet`: ese helper deja pasar un 503 y lo parsea igual
 * -pensado para `/api/health`, cuyo cuerpo en 503 tiene la misma forma que
 * en 200-. Aquí un 503 significa «el mecanismo de escritura no está
 * configurado» y su cuerpo es `{detail}`, no un `Objectives`; tratarlo
 * igual que cualquier otro fallo y devolver `null` es lo correcto.
 */
export async function getObjectives(): Promise<Objectives | null> {
  try {
    const response = await fetch(`${API_INTERNAL_URL}/api/profile/objectives`, {
      headers: await cookieHeaders(),
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as Objectives;
  } catch {
    return null;
  }
}

export function diffObjectives(
  edit: EditableObjectives,
): Promise<PostResult<ObjectivesDiff>> {
  return apiPost<ObjectivesDiff>("/api/profile/objectives/diff", edit);
}

export function commitObjectives(
  edit: EditableObjectives,
): Promise<PostResult<ObjectivesCommit>> {
  return apiPost<ObjectivesCommit>("/api/profile/objectives/commit", edit);
}

/**
 * `config/preferences.yaml`, Fase 2 M1. Ninguna de sus nueve claves es
 * vocabulario de código -comprobado por grep antes de construir este
 * módulo-, así que no hay ningún `Record` de etiquetas que mantener aquí,
 * a diferencia de `role_families`.
 */
export type Preferences = {
  version: number;
  updated_at: string;
  work_content: {
    preference: string;
    avoid_narrow_specialization: boolean;
    client_facing: string;
    programming: string;
    travel: string;
  };
  work_intensity: {
    willing_to_accept_high_intensity: boolean;
    intended_duration_years: [number, number];
    condition: string;
  };
  work_mode: { onsite: string; hybrid: string; remote: string };
  geography: {
    eu_passport: boolean;
    visa_sponsorship: string;
    countries: string;
    madrid_advantage: string;
  };
  compensation: {
    spain_minimum_gross_eur: number;
    current_madrid_gross_eur: number;
    current_madrid_net_monthly_eur: number;
    current_madrid_payments_per_year: number;
    current_living_costs_monthly_eur: [number, number];
    current_annual_savings_eur: number;
    savings_baseline_note: string;
    abroad_housing_assumption: string;
    outside_madrid_rule: string;
    international_targets: string;
  };
  language: {
    spanish: string;
    english_interview: string;
    evidence: string[];
    cv_policy: string;
  };
  professional_project_documentation: {
    contribution_granularity: string;
    avoid_internal_task_breakdown: boolean;
    acceptable_evidence: string;
    cv_implication: string;
  };
};

export type EditablePreferences = Omit<Preferences, "version" | "updated_at">;
export type PreferencesDiff = { diff: string; validated: Preferences };
export type PreferencesCommit = { commit_sha: string; diff: string };

export async function getPreferences(): Promise<Preferences | null> {
  try {
    const response = await fetch(`${API_INTERNAL_URL}/api/profile/preferences`, {
      headers: await cookieHeaders(),
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as Preferences;
  } catch {
    return null;
  }
}

export function diffPreferences(
  edit: EditablePreferences,
): Promise<PostResult<PreferencesDiff>> {
  return apiPost<PreferencesDiff>("/api/profile/preferences/diff", edit);
}

export function commitPreferences(
  edit: EditablePreferences,
): Promise<PostResult<PreferencesCommit>> {
  return apiPost<PreferencesCommit>("/api/profile/preferences/commit", edit);
}

/**
 * `config/constraints.yaml`, Fase 2 M1.
 *
 * `superseded_decisions` es un mapa de clave -> texto en el YAML, pero
 * viaja aquí como lista ordenada de pares: es lo que permite editarlo con
 * un formulario de filas -añadir, editar, quitar- en vez de un objeto de
 * claves dinámicas. `constraints.py` hace la conversión de vuelta al
 * escribir.
 */
export type DisqualifyingCondition = { id: string; rule: string };
export type SupersededDecision = { key: string; text: string };

export type Constraints = {
  version: number;
  updated_at: string;
  hard_constraints: string[];
  current_known_constraints: {
    timing: string;
    spain_salary_floor_gross_eur: number;
    relocation: string;
    visa_sponsorship: string;
    eu_work_authorization: boolean;
  };
  sector_policy: {
    excluded_industries: string[];
    rule: string;
    note: string;
  };
  disqualifying_conditions: DisqualifyingCondition[];
  accepted_conditions: {
    on_call_and_shift_work: string;
    high_intensity: string;
  };
  pending_decisions: string[];
  superseded_decisions: SupersededDecision[];
};

export type EditableConstraints = Omit<Constraints, "version" | "updated_at">;
export type ConstraintsDiff = { diff: string; validated: Constraints };
export type ConstraintsCommit = { commit_sha: string; diff: string };

export async function getConstraints(): Promise<Constraints | null> {
  try {
    const response = await fetch(`${API_INTERNAL_URL}/api/profile/constraints`, {
      headers: await cookieHeaders(),
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as Constraints;
  } catch {
    return null;
  }
}

export function diffConstraints(
  edit: EditableConstraints,
): Promise<PostResult<ConstraintsDiff>> {
  return apiPost<ConstraintsDiff>("/api/profile/constraints/diff", edit);
}

export function commitConstraints(
  edit: EditableConstraints,
): Promise<PostResult<ConstraintsCommit>> {
  return apiPost<ConstraintsCommit>("/api/profile/constraints/commit", edit);
}
