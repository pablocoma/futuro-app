"use server";

import { redirect } from "next/navigation";

import { ingestOffer } from "@/lib/api";

export type CaptureState = { error: string | null };

/**
 * El mismo mínimo que exige la API, comprobado también aquí.
 *
 * No es desconfianza del backend —que sigue siendo quien manda— sino
 * idioma: el 422 de la API trae el mensaje de pydantic, en inglés, y quien
 * acaba de pegar un anuncio no tiene por qué leer eso.
 */
const MIN_CHARS = 200;

/**
 * Guarda el anuncio pegado y lleva a su pantalla.
 *
 * Una captura repetida no es un error: la API devuelve la oferta que ya
 * había, y llevar ahí es exactamente lo que quiere quien acaba de pegar el
 * mismo anuncio dos veces.
 */
export async function captureOffer(
  _previous: CaptureState,
  formData: FormData,
): Promise<CaptureState> {
  const rawText = String(formData.get("raw_text") ?? "").trim();
  const note = String(formData.get("capture_note") ?? "").trim();
  if (!rawText) {
    return { error: "Pega el texto del anuncio." };
  }
  if (rawText.length < MIN_CHARS) {
    return {
      error: `El anuncio son ${rawText.length} caracteres y hacen falta al menos ${MIN_CHARS}: con menos, no hay nada que extraer.`,
    };
  }

  const result = await ingestOffer({
    raw_text: rawText,
    ...(note ? { capture_note: note } : {}),
  });
  if (!result.ok) {
    return { error: result.detail };
  }
  // Fuera del try: `redirect` funciona lanzando, así que capturarlo lo
  // convertiría en un error de la pantalla.
  redirect(`/ofertas/${result.data.capture_id}`);
}
