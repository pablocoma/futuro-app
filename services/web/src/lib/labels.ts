/**
 * Cómo se llama cada campo en pantalla.
 *
 * Vive en el frontend porque es presentación: el nombre de una columna no
 * tiene por qué viajar traducido en cada respuesta de la API. Un campo sin
 * etiqueta se pinta con su nombre técnico, que es feo pero no oculta nada:
 * añadir un campo al contrato lo hace aparecer igualmente.
 */
export const FIELD_LABELS: Record<string, string> = {
  title: "Puesto",
  role_family: "Familia",
  seniority_label: "Seniority",
  experience_years_required: "Años exigidos",
  location: "Ubicación",
  work_mode: "Modalidad",
  hiring_regions: "Regiones de contratación",
  language_of_work: "Idiomas de trabajo",
  contract_vehicle: "Vía de contratación",
  posting_status: "Estado del anuncio",
  comp_amount_min: "Mínimo",
  comp_amount_max: "Máximo",
  comp_currency: "Moneda",
  comp_period: "Periodo",
  comp_basis: "Base",
  comp_bonus_pct: "Bonus (%)",
  comp_bonus_type: "Tipo de bonus",
  comp_equity: "Equity",
  comp_territorial_adjustment: "Ajuste territorial",
  responsibilities: "Responsabilidades",
  posting_company_id: "Quien publica",
  employer_company_id: "Empleador final",
};

export const REQUIREMENT_KINDS: Record<string, string> = {
  mandatory: "imprescindible",
  desirable: "deseable",
  anomalous: "anómalo",
};

export const STATUS_LABELS: Record<string, string> = {
  none: "sin extraer",
  queued: "en cola",
  running: "extrayendo",
  succeeded: "extraída",
  failed: "fallida",
};

export const ASSESSMENT_STATUS_LABELS: Record<string, string> = {
  none: "sin puntuar",
  queued: "en cola",
  running: "puntuando",
  succeeded: "puntuada",
  failed: "fallida",
};

/**
 * Los estados de los filtros, los cubos de cartera y los niveles de
 * esfuerzo. Estos sí se traducen aquí porque son vocabulario de **código**:
 * la aplicación ramifica sobre ellos para calcular, así que no pueden
 * cambiar de nombre desde el YAML.
 *
 * Los nombres de dimensión y de filtro, en cambio, viven en
 * `config/scoring_model.yaml` del repositorio privado y **no** tienen mapa
 * aquí: traducirlos sería duplicar en este repositorio público el
 * vocabulario del privado, que es justo lo que no se hace. Se pintan
 * humanizando el identificador, y el día que hagan falta etiquetas de
 * verdad, van en ese YAML.
 */
export const GATE_STATUS_LABELS: Record<string, string> = {
  pass: "cumple",
  stretch: "justo por debajo",
  pending: "sin comprobar",
  fail: "no cumple",
};

export const PORTFOLIO_LABELS: Record<string, string> = {
  realistic: "realista",
  realistic_stretch: "realista con esfuerzo",
  aspirational: "aspiracional",
  experimental: "experimental",
  discard: "descartar",
};

export const EFFORT_LABELS: Record<string, string> = {
  full: "candidatura completa",
  standard: "variante base con ajuste mínimo",
  cheap: "solo si postularse es barato",
  skip: "registrar y no enviar",
};

export const PROBABILITY_LABELS: Record<string, string> = {
  high: "alta",
  medium: "media",
  low: "baja",
  very_low: "muy baja",
};

export const MATCH_LABELS: Record<string, string> = {
  meets: "cumple",
  partial: "parcial",
  no_evidence: "sin evidencia",
};

/**
 * Un identificador del repositorio de datos, legible.
 *
 * `career_capital_and_brand` → «Career capital and brand». No se traduce: el
 * vocabulario es del repositorio privado y aquí no se duplica. Humanizar el
 * identificador es feo y no oculta nada, que es el mismo criterio que
 * `labelFor` aplica a un campo sin etiqueta.
 */
export function humanise(identifier: string): string {
  const words = identifier.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function labelFor(name: string): string {
  return FIELD_LABELS[name] ?? name;
}

/** Un valor de la API, listo para pintar. */
export function displayValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(" · ") : null;
  }
  return String(value);
}
