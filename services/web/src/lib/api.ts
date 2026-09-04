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
