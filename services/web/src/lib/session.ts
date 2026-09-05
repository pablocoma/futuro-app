import { redirect } from "next/navigation";

import { getCurrentUser, type CurrentUser } from "@/lib/api";

/**
 * Exige sesión para pintar una pantalla, o devuelve a la de inicio.
 *
 * La API es quien manda: sus rutas ya responden 401 sin sesión, así que sin
 * esto no había agujero de seguridad, solo una pantalla que se dejaba usar
 * para acabar en un error en inglés al enviar. Esto es lo que evita esa
 * pantalla inútil.
 *
 * Se pregunta a la API en vez de mirar si existe la cookie, por dos motivos:
 * la cookie va firmada y desde aquí no se puede validar, y en desarrollo
 * `DEV_AUTH_BYPASS` autentica **sin** cookie, así que un guardián basado en
 * su presencia mandaría a la pantalla de inicio en local y rompería el E2E.
 *
 * Ese mismo bypass es la razón de que el fallo llegara a producción: en
 * local todo parece autenticado siempre, y el caso sin sesión no existe.
 */
export async function requireUser(): Promise<CurrentUser> {
  const user = await getCurrentUser();
  if (!user) {
    redirect("/");
  }
  return user;
}
