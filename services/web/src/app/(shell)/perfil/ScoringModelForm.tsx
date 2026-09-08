"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type {
  DimensionEdit,
  EffortTier,
  GateEdit,
  LabeledTextRow,
  ScoringModel,
} from "@/lib/api";

import { reviewScoringModel, type ScoringModelFormState } from "./actions";

const INITIAL_SCORING_MODEL_STATE: ScoringModelFormState = {
  error: null,
  diff: null,
  saved: false,
  commitSha: null,
};

const inputClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5 text-sm";
const textareaClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-2 text-sm";
const captionClass = "block text-ink2";
const sectionTitleClass = "font-mono text-xs uppercase tracking-widest text-ink3";

const EFFORT_TIER_LABELS: Record<EffortTier, string> = {
  full: "Full",
  standard: "Standard",
  cheap: "Cheap",
  skip: "Skip",
};

/**
 * Filas «etiqueta -> texto» de longitud variable, sin identificador
 * estable -mismo patrón que `SkillsEditor` de `RoleVariantsForm`-. Las
 * reutilizan las anclas de una dimensión (niveles `0`/`1`/`3`/`5` más
 * notas libres) y los filtros (`pass`/`fail`/`context`/...).
 */
function LabeledTextRowsEditor({
  rows,
  onChange,
  rowLabelPrefix,
}: {
  rows: LabeledTextRow[];
  onChange: (rows: LabeledTextRow[]) => void;
  rowLabelPrefix: string;
}) {
  function update(index: number, changes: Partial<LabeledTextRow>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function addRow() {
    onChange([...rows, { label: "", text: "" }]);
  }

  return (
    <div className="space-y-2">
      {rows.map((row, index) => (
        <div key={index} className="flex flex-wrap items-start gap-2">
          <input
            type="text"
            placeholder="etiqueta (0, 1, 3, 5, assumption, pass, fail...)"
            aria-label={`Etiqueta de la fila ${index + 1} de ${rowLabelPrefix}`}
            value={row.label}
            onChange={(e) => update(index, { label: e.target.value })}
            className={`${inputClass} sm:w-56`}
          />
          <textarea
            rows={2}
            placeholder="texto"
            aria-label={`Texto de la fila ${index + 1} de ${rowLabelPrefix}`}
            value={row.text}
            onChange={(e) => update(index, { text: e.target.value })}
            className={`${textareaClass} flex-1`}
          />
          <button type="button" onClick={() => removeRow(index)} className="btn-link">
            Quitar
          </button>
        </div>
      ))}
      <button type="button" onClick={addRow} className="btn-link">
        + Añadir fila
      </button>
    </div>
  );
}

function DimensionEditor({
  index,
  dimension,
  onChange,
  onRemove,
}: {
  index: number;
  dimension: DimensionEdit;
  onChange: (dimension: DimensionEdit) => void;
  onRemove: () => void;
}) {
  // Etiquetas por posición (`index`), no por `dimension.name`: el nombre es
  // justo el campo que se está editando, así que usarlo como identificador
  // de su propia etiqueta cambiaría de valor mientras se escribe.
  return (
    <div className="space-y-3 rounded-lg border border-white/10 p-4">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex-1 space-y-1 text-sm">
          <span className={captionClass}>Nombre de la dimensión</span>
          <input
            type="text"
            aria-label={`Nombre de la dimensión ${index + 1}`}
            value={dimension.name}
            onChange={(e) => onChange({ ...dimension, name: e.target.value })}
            className={inputClass}
          />
        </label>
        <label className="w-28 space-y-1 text-sm">
          <span className={captionClass}>Peso</span>
          <input
            type="number"
            min={1}
            aria-label={`Peso de la dimensión ${index + 1}`}
            value={dimension.weight}
            onChange={(e) => onChange({ ...dimension, weight: Number(e.target.value) })}
            className={inputClass}
          />
        </label>
        <button type="button" onClick={onRemove} className="btn-link">
          Quitar dimensión
        </button>
      </div>
      <div className="space-y-1 text-sm">
        <span className={captionClass}>Anclas</span>
        <LabeledTextRowsEditor
          rows={dimension.anchors}
          onChange={(anchors) => onChange({ ...dimension, anchors })}
          rowLabelPrefix={`la dimensión ${index + 1}`}
        />
      </div>
    </div>
  );
}

function GateEditor({
  index,
  gate,
  onChange,
  onRemove,
}: {
  index: number;
  gate: GateEdit;
  onChange: (gate: GateEdit) => void;
  onRemove: () => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-white/10 p-4">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex-1 space-y-1 text-sm">
          <span className={captionClass}>Nombre del filtro</span>
          <input
            type="text"
            aria-label={`Nombre del filtro ${index + 1}`}
            value={gate.name}
            onChange={(e) => onChange({ ...gate, name: e.target.value })}
            className={inputClass}
          />
        </label>
        <button type="button" onClick={onRemove} className="btn-link">
          Quitar filtro
        </button>
      </div>
      <div className="space-y-1 text-sm">
        <span className={captionClass}>Criterios</span>
        <LabeledTextRowsEditor
          rows={gate.rows}
          onChange={(rows) => onChange({ ...gate, rows })}
          rowLabelPrefix={`el filtro ${index + 1}`}
        />
      </div>
    </div>
  );
}

function EffortOrderEditor({
  order,
  onChange,
}: {
  order: EffortTier[];
  onChange: (order: EffortTier[]) => void;
}) {
  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= order.length) return;
    const next = [...order];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <ol className="space-y-1">
      {order.map((tier, index) => (
        <li
          key={tier}
          className="flex items-center justify-between rounded-md border border-white/10 px-3 py-1.5 text-sm"
        >
          <span>
            {index + 1}. {EFFORT_TIER_LABELS[tier]}
          </span>
          <span className="flex gap-2">
            <button
              type="button"
              onClick={() => move(index, -1)}
              disabled={index === 0}
              className="btn-link disabled:opacity-30"
              aria-label={`Subir ${EFFORT_TIER_LABELS[tier]}`}
            >
              ▲
            </button>
            <button
              type="button"
              onClick={() => move(index, 1)}
              disabled={index === order.length - 1}
              className="btn-link disabled:opacity-30"
              aria-label={`Bajar ${EFFORT_TIER_LABELS[tier]}`}
            >
              ▼
            </button>
          </span>
        </li>
      ))}
    </ol>
  );
}

function ParagraphListEditor({
  values,
  onChange,
}: {
  values: string[];
  onChange: (values: string[]) => void;
}) {
  function update(index: number, value: string) {
    onChange(values.map((v, i) => (i === index ? value : v)));
  }

  function removeRow(index: number) {
    onChange(values.filter((_, i) => i !== index));
  }

  function addRow() {
    onChange([...values, ""]);
  }

  return (
    <div className="space-y-2">
      {values.map((value, index) => (
        <div key={index} className="flex flex-wrap items-start gap-2">
          <textarea
            rows={2}
            aria-label={`Nota ${index + 1}`}
            value={value}
            onChange={(e) => update(index, e.target.value)}
            className={`${textareaClass} flex-1`}
          />
          <button type="button" onClick={() => removeRow(index)} className="btn-link">
            Quitar
          </button>
        </div>
      ))}
      <button type="button" onClick={addRow} className="btn-link">
        + Añadir nota
      </button>
    </div>
  );
}

/**
 * `config/scoring_model.yaml`, Fase 2 M4 -- la última rebanada de Fase 2.
 *
 * De solo lectura, sin ningún camino de edición -decidido con Pablo el
 * 2026-09-08, mismo criterio que `claim_rules`/`fixed_sections` en M3-:
 * `version`, `status`, el nombre del bloque de línea base, `scale`, y el
 * bloque entero de `portfolio_assignment` + cada nivel de
 * `output.effort_tier` (`when`/`do`) + `output.required_fields` +
 * `missing_data.rule/method/coverage/below_minimum`. Esa prosa documenta
 * umbrales que en realidad decide a mano `assessment/scoring.py`; se
 * enseña igualmente aquí, de solo lectura, para que quede claro por qué
 * el orden de esfuerzo hace lo que hace -el mismo motivo por el que
 * `output.effort_tier.evaluation_order` sí es la excepción editable-.
 */
export function ScoringModelForm({ current }: { current: ScoringModel }) {
  const [description, setDescription] = useState(current.description);
  const [baseline, setBaseline] = useState(current.baseline);
  const [dimensions, setDimensions] = useState<DimensionEdit[]>(current.dimensions);
  const [gates, setGates] = useState<GateEdit[]>(current.gates);
  const [probabilityBands, setProbabilityBands] = useState(current.probability_bands);
  const [minimumCoverage, setMinimumCoverage] = useState(current.minimum_coverage);
  const [neverRule, setNeverRule] = useState(current.never_rule);
  const [effortOrder, setEffortOrder] = useState<EffortTier[]>(
    current.effort_evaluation_order,
  );
  const [portfolioPolicy, setPortfolioPolicy] = useState(current.portfolio_policy);
  const [notes, setNotes] = useState<string[]>(current.notes);

  const [state, action, pending] = useActionState<ScoringModelFormState, FormData>(
    reviewScoringModel,
    INITIAL_SCORING_MODEL_STATE,
  );
  const router = useRouter();

  useEffect(() => {
    if (state.saved) router.refresh();
  }, [state.saved, router]);

  const effortTierDetail = current.output.effort_tier as Record<
    string,
    { when?: string; do?: string }
  >;

  return (
    <form action={action} className="space-y-8">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Modelo de scoring</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} ({current.status}) · actualizado el{" "}
          {current.updated_at} · línea base «{current.baseline_name}», de solo
          lectura
        </p>
      </header>

      <input type="hidden" name="baseline_json" value={JSON.stringify(baseline)} />
      <input type="hidden" name="dimensions_json" value={JSON.stringify(dimensions)} />
      <input type="hidden" name="gates_json" value={JSON.stringify(gates)} />
      <input
        type="hidden"
        name="probability_bands_json"
        value={JSON.stringify(probabilityBands)}
      />
      <input
        type="hidden"
        name="effort_evaluation_order_json"
        value={JSON.stringify(effortOrder)}
      />
      <input
        type="hidden"
        name="portfolio_policy_json"
        value={JSON.stringify(portfolioPolicy)}
      />
      <input type="hidden" name="notes_json" value={JSON.stringify(notes)} />

      <section className="space-y-2">
        <h3 className={sectionTitleClass}>Descripción</h3>
        <textarea
          rows={3}
          name="description"
          aria-label="Descripción del modelo"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className={textareaClass}
        />
      </section>

      <section className="space-y-3">
        <h3 className={sectionTitleClass}>Línea base económica</h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {(
            [
              ["gross_annual_eur", "Bruto anual (EUR)"],
              ["payments_per_year", "Pagas al año"],
              ["net_monthly_eur", "Neto mensual (EUR)"],
              ["net_annual_eur", "Neto anual (EUR)"],
              ["reference_savings_eur", "Ahorro de referencia (EUR)"],
              ["savings_rate", "Tasa de ahorro (0-1)"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="space-y-1 text-sm">
              <span className={captionClass}>{label}</span>
              <input
                type="number"
                step={key === "savings_rate" ? 0.01 : 1}
                aria-label={label}
                value={baseline[key]}
                onChange={(e) =>
                  setBaseline({ ...baseline, [key]: Number(e.target.value) })
                }
                className={inputClass}
              />
            </label>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-2">
          <div className="flex gap-2">
            <label className="flex-1 space-y-1 text-sm">
              <span className={captionClass}>Coste de vida mensual, mínimo (EUR)</span>
              <input
                type="number"
                aria-label="Coste de vida mensual, mínimo"
                value={baseline.living_costs_monthly_eur[0]}
                onChange={(e) =>
                  setBaseline({
                    ...baseline,
                    living_costs_monthly_eur: [
                      Number(e.target.value),
                      baseline.living_costs_monthly_eur[1],
                    ],
                  })
                }
                className={inputClass}
              />
            </label>
            <label className="flex-1 space-y-1 text-sm">
              <span className={captionClass}>Coste de vida mensual, máximo (EUR)</span>
              <input
                type="number"
                aria-label="Coste de vida mensual, máximo"
                value={baseline.living_costs_monthly_eur[1]}
                onChange={(e) =>
                  setBaseline({
                    ...baseline,
                    living_costs_monthly_eur: [
                      baseline.living_costs_monthly_eur[0],
                      Number(e.target.value),
                    ],
                  })
                }
                className={inputClass}
              />
            </label>
          </div>
          <div className="flex gap-2">
            <label className="flex-1 space-y-1 text-sm">
              <span className={captionClass}>Ahorro anual, mínimo (EUR)</span>
              <input
                type="number"
                aria-label="Ahorro anual, mínimo"
                value={baseline.annual_savings_eur[0]}
                onChange={(e) =>
                  setBaseline({
                    ...baseline,
                    annual_savings_eur: [
                      Number(e.target.value),
                      baseline.annual_savings_eur[1],
                    ],
                  })
                }
                className={inputClass}
              />
            </label>
            <label className="flex-1 space-y-1 text-sm">
              <span className={captionClass}>Ahorro anual, máximo (EUR)</span>
              <input
                type="number"
                aria-label="Ahorro anual, máximo"
                value={baseline.annual_savings_eur[1]}
                onChange={(e) =>
                  setBaseline({
                    ...baseline,
                    annual_savings_eur: [
                      baseline.annual_savings_eur[0],
                      Number(e.target.value),
                    ],
                  })
                }
                className={inputClass}
              />
            </label>
          </div>
        </div>
        <label className="block space-y-1 text-sm">
          <span className={captionClass}>Causa</span>
          <textarea
            rows={2}
            aria-label="Causa de la línea base"
            value={baseline.cause}
            onChange={(e) => setBaseline({ ...baseline, cause: e.target.value })}
            className={textareaClass}
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className={captionClass}>Implicación</span>
          <textarea
            rows={2}
            aria-label="Implicación de la línea base"
            value={baseline.implication}
            onChange={(e) => setBaseline({ ...baseline, implication: e.target.value })}
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-3">
        <h3 className={sectionTitleClass}>Dimensiones</h3>
        {dimensions.map((dimension, index) => (
          <DimensionEditor
            key={index}
            index={index}
            dimension={dimension}
            onChange={(next) =>
              setDimensions(dimensions.map((d, i) => (i === index ? next : d)))
            }
            onRemove={() => setDimensions(dimensions.filter((_, i) => i !== index))}
          />
        ))}
        <button
          type="button"
          onClick={() =>
            setDimensions([...dimensions, { name: "", weight: 10, anchors: [] }])
          }
          className="btn-link"
        >
          + Añadir dimensión
        </button>
      </section>

      <section className="space-y-3">
        <h3 className={sectionTitleClass}>Filtros eliminatorios</h3>
        {gates.map((gate, index) => (
          <GateEditor
            key={index}
            index={index}
            gate={gate}
            onChange={(next) => setGates(gates.map((g, i) => (i === index ? next : g)))}
            onRemove={() => setGates(gates.filter((_, i) => i !== index))}
          />
        ))}
        <button
          type="button"
          onClick={() => setGates([...gates, { name: "", rows: [] }])}
          className="btn-link"
        >
          + Añadir filtro
        </button>
      </section>

      <section className="space-y-3">
        <h3 className={sectionTitleClass}>Bandas de probabilidad</h3>
        {(["high", "medium", "low", "very_low"] as const).map((band) => (
          <label key={band} className="block space-y-1 text-sm">
            <span className={captionClass}>{band}</span>
            <textarea
              rows={2}
              aria-label={`Banda ${band}`}
              value={probabilityBands[band]}
              onChange={(e) =>
                setProbabilityBands({ ...probabilityBands, [band]: e.target.value })
              }
              className={textareaClass}
            />
          </label>
        ))}
      </section>

      <section className="space-y-3">
        <h3 className={sectionTitleClass}>Datos incompletos</h3>
        <label className="block space-y-1 text-sm">
          <span className={captionClass}>Cobertura mínima (0-1)</span>
          <input
            type="number"
            step={0.01}
            min={0}
            max={1}
            name="minimum_coverage"
            aria-label="Cobertura mínima"
            value={minimumCoverage}
            onChange={(e) => setMinimumCoverage(Number(e.target.value))}
            className={`${inputClass} sm:w-40`}
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className={captionClass}>Regla que no se salta nunca</span>
          <textarea
            rows={2}
            name="never_rule"
            aria-label="Regla que no se salta nunca"
            value={neverRule}
            onChange={(e) => setNeverRule(e.target.value)}
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-3">
        <h3 className={sectionTitleClass}>Orden de evaluación del nivel de esfuerzo</h3>
        <p className="text-sm text-ink2">
          Gana el primero que encaje. El resto de cada nivel -cuándo aplica y
          qué hacer- es de solo lectura, ver más abajo.
        </p>
        <EffortOrderEditor order={effortOrder} onChange={setEffortOrder} />
      </section>

      <section className="space-y-3">
        <h3 className={sectionTitleClass}>Política de cartera</h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {(
            [
              ["realistic", "Realistic"],
              ["realistic_stretch", "Realistic stretch"],
              ["aspirational", "Aspirational"],
              ["experimental", "Experimental"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="space-y-1 text-sm">
              <span className={captionClass}>{label}</span>
              <input
                type="number"
                step={0.01}
                min={0}
                max={1}
                aria-label={label}
                value={portfolioPolicy[key]}
                onChange={(e) =>
                  setPortfolioPolicy({
                    ...portfolioPolicy,
                    [key]: Number(e.target.value),
                  })
                }
                className={inputClass}
              />
            </label>
          ))}
        </div>
        <label className="block space-y-1 text-sm">
          <span className={captionClass}>Estado</span>
          <input
            type="text"
            aria-label="Estado de la política de cartera"
            value={portfolioPolicy.status}
            onChange={(e) =>
              setPortfolioPolicy({ ...portfolioPolicy, status: e.target.value })
            }
            className={inputClass}
          />
        </label>
        <label className="block space-y-1 text-sm">
          <span className={captionClass}>Nota</span>
          <textarea
            rows={2}
            aria-label="Nota de la política de cartera"
            value={portfolioPolicy.note}
            onChange={(e) =>
              setPortfolioPolicy({ ...portfolioPolicy, note: e.target.value })
            }
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-2">
        <h3 className={sectionTitleClass}>Notas</h3>
        <ParagraphListEditor values={notes} onChange={setNotes} />
      </section>

      <section className="space-y-3 rounded-lg border border-dashed border-white/15 p-4 text-sm text-ink3">
        <h3 className={sectionTitleClass}>
          De solo lectura: cómo decide el código hoy
        </h3>
        <p>
          Este texto documenta umbrales que en realidad decide a mano
          `assessment/scoring.py`; editarlo aquí no cambiaría cómo se puntúa
          una oferta, así que no tiene formulario -mismo criterio que
          `claim_rules`/`fixed_sections` en Variantes de CV-.
        </p>
        <div className="space-y-2">
          {Object.entries(effortTierDetail)
            .filter(([key]) => key !== "evaluation_order" && key !== "note")
            .map(([tier, detail]) => (
              <div key={tier}>
                <p className="font-mono">{tier}</p>
                {detail.when && <p>Cuándo: {detail.when}</p>}
                {detail.do && <p>Qué hacer: {detail.do}</p>}
              </div>
            ))}
        </div>
      </section>

      {state.error && <p className="font-mono text-sm text-neg">▲ {state.error}</p>}

      {state.diff !== null && (
        <section className="space-y-2">
          <h2 className={sectionTitleClass}>
            {state.saved ? "Escrito y empujado" : "Diff, sin escribir todavía"}
          </h2>
          {state.saved && state.commitSha && (
            <p className="font-mono text-sm text-pos">
              ● commit {state.commitSha.slice(0, 12)}
            </p>
          )}
          <pre className="overflow-x-auto rounded-lg border border-white/10 bg-white/[0.02] p-4 text-xs">
            {state.diff || "Sin cambios."}
          </pre>
        </section>
      )}

      <div className="flex gap-3">
        <button
          type="submit"
          name="intent"
          value="commit"
          disabled={pending || state.diff === null || state.saved}
          className="btn-primary disabled:opacity-50"
        >
          Confirmar y guardar
        </button>
        <button
          type="submit"
          name="intent"
          value="diff"
          disabled={pending}
          className="btn-link disabled:opacity-50"
        >
          Ver cambios
        </button>
      </div>
    </form>
  );
}
