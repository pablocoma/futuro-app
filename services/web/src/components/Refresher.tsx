"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Vuelve a pedir la página mientras la extracción está en marcha.
 *
 * La página se renderiza en el servidor, así que refrescar es pedirla otra
 * vez, no sondear la API desde el navegador: así el estado que se pinta y
 * el que ve el backend son el mismo, y no hay una segunda forma de leer una
 * oferta que pueda desincronizarse.
 *
 * Solo se monta cuando hay algo que esperar, y se para solo: un intervalo
 * que sigue corriendo sobre una oferta ya extraída son peticiones tiradas.
 */
export function Refresher({ everyMs = 2000 }: { everyMs?: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => router.refresh(), everyMs);
    return () => clearInterval(timer);
  }, [router, everyMs]);
  return null;
}
