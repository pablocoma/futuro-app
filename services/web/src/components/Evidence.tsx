import type { Evidence } from "@/lib/api";

/**
 * El marcador de evidencia de un campo.
 *
 * Los tres estados del contrato se pintan distinto porque significan cosas
 * distintas, y esa diferencia es el corazón del proyecto: un dato publicado
 * trae la cita literal que lo sostiene, uno inferido trae el razonamiento y
 * con cuánta confianza, y uno ausente no trae nada, porque nadie ha
 * estimado nada.
 *
 * Nunca solo por color: cada estado lleva su símbolo.
 */
export function EvidenceMark({ evidence }: { evidence: Evidence }) {
  if (evidence.status === "published") {
    return (
      <span className="font-mono text-xs text-pos" title="Consta en el anuncio">
        ● publicado
      </span>
    );
  }
  if (evidence.status === "inferred") {
    return (
      <span className="font-mono text-xs text-acc" title="Deducido del anuncio">
        ◐ inferido · {evidence.confidence ?? "sin confianza"}
      </span>
    );
  }
  // Un campo ausente no lleva marca a la derecha: su propio valor ya dice
  // «sin datos» en el color de alerta, que es la micro-decisión de
  // `docs/APP_SCREENS.md`. Ponerlo dos veces en la misma fila multiplica el
  // ruido justo donde más filas ausentes hay —la compensación, que en
  // Europa casi nunca se publica— y no añade nada.
  return null;
}

/** La prueba que sostiene el campo, debajo del valor. */
export function EvidenceDetail({ evidence }: { evidence: Evidence }) {
  if (evidence.status === "published" && evidence.source_quote) {
    return (
      <blockquote className="mt-1 border-l-2 border-pos/40 pl-2 font-mono text-xs text-ink3">
        «{evidence.source_quote}»
      </blockquote>
    );
  }
  if (evidence.status === "inferred" && evidence.reasoning) {
    return <p className="mt-1 text-xs text-ink3">{evidence.reasoning}</p>;
  }
  return null;
}
