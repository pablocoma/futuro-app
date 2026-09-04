import type { Assessment, Dimension } from "@/lib/api";
import { humanise } from "@/lib/labels";

/**
 * La composición ponderada de `docs/APP_SCREENS.md`.
 *
 * El ancho de cada barra es el peso de la dimensión en el modelo de scoring
 * y el alto es la nota. Lo que no se pudo puntuar **no se oculta ni se
 * pinta a cero**: cero es una nota, y «no se pudo puntuar» no lo es. Se
 * marca con un hueco rayado del ancho completo de la dimensión, que es lo
 * que hace que se vea cuánto peso se ha perdido de un vistazo.
 *
 * Ni un cálculo aquí. Los anchos y los altos vienen de la API, que los saca
 * de los pesos guardados con la fila; hacerlos aquí sería un segundo sitio
 * donde se calcula lo mismo, y el día que discreparan el dibujo diría una
 * cosa y la puntuación otra. Es también lo que hace que la composición de
 * una oferta puntuada hace meses siga sumando el 100% con **sus** pesos, y
 * no con los de hoy.
 *
 * Sin `<canvas>` ni librería de gráficos: son rectángulos con un ancho y un
 * alto en porcentaje, así que se renderizan en servidor y funcionan sin
 * JavaScript, igual que el resto de la pantalla.
 */
const CHART_HEIGHT = "10rem";

// Rayado diagonal para lo no puntuable, en el color de alerta de la paleta
// («señalar un dato ausente» de `APP_SCREENS.md`). Va en un `style` y no en
// una clase de Tailwind porque es un gradiente repetido con ángulo, que no
// tiene utilidad equivalente.
const HATCH = {
  backgroundImage:
    "repeating-linear-gradient(45deg, rgba(255,192,77,0.28) 0 2px," +
    " transparent 2px 6px)",
} as const;

export function Composition({ assessment }: { assessment: Assessment }) {
  const scored = assessment.dimensions.filter((d) => d.score !== null);

  return (
    <figure className="space-y-3">
      {/* `gap-0.5` y el fondo de la página detrás, y no `gap-px` sobre un
          fondo casi del mismo tono: con un solo píxel de separación, dos
          dimensiones sin puntuar contiguas se leían como un único bloque
          rayado del 30% y se perdía cuál era cuál. Se vio en una captura de
          la página, no leyendo el código. */}
      <div
        className="flex items-end gap-0.5 overflow-hidden rounded border border-white/10 bg-bg"
        style={{ height: CHART_HEIGHT }}
        role="img"
        aria-label={describe(assessment)}
      >
        {assessment.dimensions.map((dimension) => (
          <Bar key={dimension.dimension} dimension={dimension} />
        ))}
      </div>

      <div className="flex gap-0.5">
        {assessment.dimensions.map((dimension) => (
          <div
            key={dimension.dimension}
            className="min-w-0 px-1"
            style={{ width: `${dimension.weight_share * 100}%` }}
          >
            <p className="truncate font-mono text-[0.65rem] text-ink3" title={humanise(dimension.dimension)}>
              {humanise(dimension.dimension)}
            </p>
            <p className="font-mono text-[0.65rem] text-ink3">
              peso {dimension.weight}
            </p>
          </div>
        ))}
      </div>

      <figcaption className="font-mono text-xs text-ink3">
        El ancho es el peso de la dimensión; el alto, la nota. El rayado
        marca lo que no se pudo puntuar: {scored.length} de{" "}
        {assessment.dimensions.length} dimensiones tienen nota.
      </figcaption>
    </figure>
  );
}

function Bar({ dimension }: { dimension: Dimension }) {
  const width = `${dimension.weight_share * 100}%`;

  if (dimension.score === null) {
    // El hueco ocupa el alto completo a propósito: lo que se enseña no es
    // una nota baja, es que ahí falta información y cuánto peso se lleva.
    return (
      <div
        className="flex h-full items-center justify-center rounded-sm border border-dashed border-neg/40"
        style={{ width, ...HATCH }}
        title={dimension.unscored_reason ?? "sin puntuar"}
      >
        <span className="font-mono text-xs text-neg">—</span>
      </div>
    );
  }

  // Un cero **es una nota**, y esa distinción es medio proyecto. Con la
  // altura proporcional a secas se pintaba una columna vacía,
  // indistinguible de un hueco: se vio en la primera puntuación con el
  // modelo de verdad, donde `compensation_upside` sacó un 0 y desaparecía.
  // El mínimo de dos píxeles le deja una línea de base visible, y el número
  // se saca fuera de la barra cuando no cabe dentro.
  const zero = dimension.score === 0;

  return (
    <div className="flex h-full flex-col justify-end" style={{ width }}>
      {zero ? (
        <span className="pb-0.5 text-center font-mono text-xs text-pos">0</span>
      ) : null}
      <div
        className="flex items-start justify-center bg-pos/70"
        style={{
          height: `${(dimension.score_share ?? 0) * 100}%`,
          minHeight: "2px",
        }}
      >
        {zero ? null : (
          <span className="pt-0.5 font-mono text-xs text-bg">
            {dimension.score}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * El dibujo, en palabras, para quien no lo ve.
 *
 * El gráfico entero es una sola imagen con su descripción en vez de un
 * montón de divs sueltos: leer «40%, 3, 30%, 3, 20%, sin puntuar» celda a
 * celda no dice nada. El detalle campo a campo está debajo en texto, que es
 * donde se puede leer de verdad.
 */
function describe(assessment: Assessment): string {
  const parts = assessment.dimensions.map((dimension) => {
    const name = humanise(dimension.dimension);
    if (dimension.score === null) {
      return `${name}, peso ${dimension.weight}, sin puntuar`;
    }
    return `${name}, peso ${dimension.weight}, nota ${dimension.score} de 5`;
  });
  return `Composición ponderada: ${parts.join("; ")}.`;
}
