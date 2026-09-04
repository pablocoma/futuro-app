import { describe, expect, it } from "vitest";

import {
  EFFORT_LABELS,
  GATE_STATUS_LABELS,
  PORTFOLIO_LABELS,
  PROBABILITY_LABELS,
  humanise,
} from "@/lib/labels";

describe("etiquetas de la puntuación", () => {
  it("humaniza un identificador del repositorio de datos sin traducirlo", () => {
    // No hay mapa de traducción para los nombres de dimensión y de filtro a
    // propósito: viven en `config/scoring_model.yaml` del repositorio
    // privado, y tener aquí un diccionario sería duplicar en un repositorio
    // público el vocabulario del privado. Feo, y no oculta nada.
    expect(humanise("expected_net_savings")).toBe("Expected net savings");
    expect(humanise("ahorro_estimado")).toBe("Ahorro estimado");
  });

  it("no se atraganta con un identificador raro", () => {
    expect(humanise("")).toBe("");
    expect(humanise("x")).toBe("X");
  });

  it("cubre los vocabularios de código enteros", () => {
    // Estos tres sí se traducen porque son de código: la aplicación
    // ramifica sobre ellos para calcular, así que no pueden cambiar de
    // nombre desde el YAML. Y si alguno se quedara sin etiqueta, la
    // pantalla enseñaría el identificador técnico sin que nadie se enterara.
    expect(Object.keys(GATE_STATUS_LABELS).sort()).toEqual([
      "fail",
      "pass",
      "pending",
      "stretch",
    ]);
    expect(Object.keys(PORTFOLIO_LABELS).sort()).toEqual([
      "aspirational",
      "discard",
      "experimental",
      "realistic",
      "realistic_stretch",
    ]);
    expect(Object.keys(EFFORT_LABELS).sort()).toEqual([
      "cheap",
      "full",
      "skip",
      "standard",
    ]);
    expect(Object.keys(PROBABILITY_LABELS).sort()).toEqual([
      "high",
      "low",
      "medium",
      "very_low",
    ]);
  });

  it("distingue «sin comprobar» de «no cumple»", () => {
    // Es la confusión que el modelo de scoring prohíbe: un filtro que no se
    // puede evaluar queda pendiente, y nunca se supone superado ni
    // incumplido.
    expect(GATE_STATUS_LABELS.pending).not.toBe(GATE_STATUS_LABELS.fail);
    expect(GATE_STATUS_LABELS.pending).toBe("sin comprobar");
  });
});
