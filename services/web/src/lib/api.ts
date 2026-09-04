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
