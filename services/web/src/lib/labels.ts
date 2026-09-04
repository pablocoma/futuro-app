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
