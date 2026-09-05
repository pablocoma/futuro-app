"use server";

import { revalidatePath } from "next/cache";

import { assessOffer, confirmVariant as confirmVariantCall } from "@/lib/api";

/**
 * Pide puntuar una oferta otra vez.
 *
 * En el camino normal no hace falta: la extracción encadena la puntuación
 * al terminar bien. Este botón existe para los casos en los que eso no
 * pasó —el encolado falló, el repositorio de datos no estaba— y para
 * repuntuar a mano tras tocar el modelo de scoring.
 *
 * Va como acción de servidor y no como `fetch` desde el navegador para que
 * el estado que se pinta y el que ve el backend sigan siendo el mismo, que
 * es la decisión de M1 sobre el refresco de esta pantalla. `revalidatePath`
 * hace que la vuelta ya traiga el trabajo en cola.
 *
 * Sobre la autorización, que la documentación de Next avisa de que hay que
 * comprobar en cada acción de servidor porque son alcanzables por POST
 * directo: aquí no se comprueba y no hace falta, porque esta función no
 * escribe nada. Lo único que hace es llamar a la API reenviando la cookie
 * de sesión, y la API está cerrada por omisión: sin sesión válida responde
 * 401 y esto queda en nada. La autorización vive en un solo sitio, que es
 * donde está el dato.
 */
export async function requestAssessment(formData: FormData): Promise<void> {
  const id = String(formData.get("capture_id") ?? "");
  if (!id) {
    return;
  }
  await assessOffer(id);
  revalidatePath(`/ofertas/${id}`);
}

/**
 * Confirma o cambia la variante de CV de una oferta.
 *
 * Igual patrón que `requestAssessment` y por el mismo motivo: acción de
 * servidor, sin `fetch` desde el navegador, con `revalidatePath` para que
 * la vuelta ya enseñe el dossier confirmado. Nunca sobrescribe una
 * confirmación anterior -eso lo decide la API creando una fila nueva-, así
 * que esto solo necesita pedirle a la API que lo haga y refrescar.
 */
export async function confirmVariant(formData: FormData): Promise<void> {
  const id = String(formData.get("capture_id") ?? "");
  const variant = String(formData.get("variant") ?? "");
  if (!id || !variant) {
    return;
  }
  await confirmVariantCall(id, variant);
  revalidatePath(`/ofertas/${id}`);
}
