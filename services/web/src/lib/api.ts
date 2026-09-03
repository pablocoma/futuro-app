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
};

export type CurrentUser = {
  email: string;
  via: string;
};

/**
 * Llama a la API reenviando las cookies de la petición entrante, que es lo
 * que permite que un Server Component vea la misma sesión que el navegador.
 *
 * Devuelve `null` en 401 y en fallo de red: el consumidor distingue "no hay
 * sesión" y "no hay API" por el endpoint que estaba consultando, y ninguna
 * pantalla de M0 debe romperse porque la API esté caída.
 */
async function apiGet<T>(path: string): Promise<T | null> {
  const cookieHeader = (await cookies()).toString();
  try {
    const response = await fetch(`${API_INTERNAL_URL}${path}`, {
      headers: cookieHeader ? { cookie: cookieHeader } : {},
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

export function getHealth(): Promise<Health | null> {
  return apiGet<Health>("/api/health");
}

export function getCurrentUser(): Promise<CurrentUser | null> {
  return apiGet<CurrentUser>("/api/auth/me");
}
