"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { Constraints, DisqualifyingCondition, SupersededDecision } from "@/lib/api";

import { reviewConstraints, type ConstraintsFormState } from "./actions";

const INITIAL_CONSTRAINTS_STATE: ConstraintsFormState = {
  error: null,
  diff: null,
  saved: false,
  commitSha: null,
};

type FormValues = {
  hardConstraints: string;
  timing: string;
  spainSalaryFloorGrossEur: string;
  relocation: string;
  visaSponsorship: string;
  euWorkAuthorization: boolean;
  excludedIndustries: string;
  sectorRule: string;
  sectorNote: string;
  disqualifyingConditions: DisqualifyingCondition[];
  onCallAndShiftWork: string;
  highIntensity: string;
  pendingDecisions: string;
  supersededDecisions: SupersededDecision[];
};

function valuesFrom(current: Constraints): FormValues {
  return {
    hardConstraints: current.hard_constraints.join(", "),
    timing: current.current_known_constraints.timing,
    spainSalaryFloorGrossEur: String(
      current.current_known_constraints.spain_salary_floor_gross_eur,
    ),
    relocation: current.current_known_constraints.relocation,
    visaSponsorship: current.current_known_constraints.visa_sponsorship,
    euWorkAuthorization: current.current_known_constraints.eu_work_authorization,
    excludedIndustries: current.sector_policy.excluded_industries.join(", "),
    sectorRule: current.sector_policy.rule,
    sectorNote: current.sector_policy.note,
    disqualifyingConditions: current.disqualifying_conditions,
    onCallAndShiftWork: current.accepted_conditions.on_call_and_shift_work,
    highIntensity: current.accepted_conditions.high_intensity,
    pendingDecisions: current.pending_decisions.join(", "),
    supersededDecisions: current.superseded_decisions,
  };
}

const inputClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5 text-sm";
const textareaClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-2 text-sm";
const labelClass = "block space-y-1 text-sm";
const captionClass = "block text-ink2";
const sectionTitleClass = "font-mono text-xs uppercase tracking-widest text-ink3";

/**
 * `disqualifying_conditions`: añadir filas y editar el `rule` de las que
 * ya existen, sin borrar ni reordenar -alcance confirmado con Pablo el
 * 2026-09-07-. Por eso `id` es de solo lectura en una fila existente: el
 * backend casa por `id`, y dejar que se edite libremente crearía una fila
 * nueva sin borrar la vieja en vez de renombrar nada.
 */
function DisqualifyingConditionsEditor({
  rows,
  onChange,
}: {
  rows: DisqualifyingCondition[];
  onChange: (rows: DisqualifyingCondition[]) => void;
}) {
  const [newId, setNewId] = useState("");
  const [newRule, setNewRule] = useState("");

  function updateRule(index: number, rule: string) {
    onChange(rows.map((row, i) => (i === index ? { ...row, rule } : row)));
  }

  function addRow() {
    const id = newId.trim();
    const rule = newRule.trim();
    if (!id || !rule) return;
    onChange([...rows, { id, rule }]);
    setNewId("");
    setNewRule("");
  }

  return (
    <div className="space-y-3">
      <input type="hidden" name="disqualifying_conditions_json" value={JSON.stringify(rows)} />
      <div className="divide-y divide-white/5 rounded-lg border border-white/10">
        {rows.map((row, index) => (
          <div key={row.id} className="space-y-2 px-4 py-3">
            <p className="font-mono text-xs text-ink3">{row.id}</p>
            <textarea
              rows={2}
              value={row.rule}
              onChange={(e) => updateRule(index, e.target.value)}
              className={textareaClass}
            />
          </div>
        ))}
      </div>
      <div className="space-y-2 rounded-lg border border-dashed border-white/15 p-4">
        <p className={captionClass}>Añadir una condición nueva</p>
        <input
          type="text"
          placeholder="identificador"
          value={newId}
          onChange={(e) => setNewId(e.target.value)}
          className={inputClass}
        />
        <textarea
          rows={2}
          placeholder="regla"
          value={newRule}
          onChange={(e) => setNewRule(e.target.value)}
          className={textareaClass}
        />
        <button type="button" onClick={addRow} className="btn-link">
          + Añadir condición
        </button>
      </div>
    </div>
  );
}

/** `superseded_decisions`: CRUD completo -añadir, editar, quitar-,
 * decidido con Pablo el 2026-09-07. A diferencia de las condiciones
 * descalificantes, aquí no hay ningún backend que case por identificador
 * estable entre pantallas, así que la clave también es editable. */
function SupersededDecisionsEditor({
  rows,
  onChange,
}: {
  rows: SupersededDecision[];
  onChange: (rows: SupersededDecision[]) => void;
}) {
  function updateKey(index: number, key: string) {
    onChange(rows.map((row, i) => (i === index ? { ...row, key } : row)));
  }

  function updateText(index: number, text: string) {
    onChange(rows.map((row, i) => (i === index ? { ...row, text } : row)));
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function addRow() {
    onChange([...rows, { key: "", text: "" }]);
  }

  return (
    <div className="space-y-3">
      <input type="hidden" name="superseded_decisions_json" value={JSON.stringify(rows)} />
      <div className="space-y-3">
        {rows.map((row, index) => (
          <div
            key={index}
            className="space-y-2 rounded-lg border border-white/10 p-4"
          >
            <input
              type="text"
              placeholder="clave"
              value={row.key}
              onChange={(e) => updateKey(index, e.target.value)}
              className={inputClass}
            />
            <textarea
              rows={2}
              placeholder="texto"
              value={row.text}
              onChange={(e) => updateText(index, e.target.value)}
              className={textareaClass}
            />
            <button
              type="button"
              onClick={() => removeRow(index)}
              className="btn-link"
            >
              Quitar
            </button>
          </div>
        ))}
      </div>
      <button type="button" onClick={addRow} className="btn-link">
        + Añadir decisión sustituida
      </button>
    </div>
  );
}

/** Campos controlados, no `defaultValue` -mismo hallazgo que
 * `ObjectivesForm`-. */
export function ConstraintsForm({ current }: { current: Constraints }) {
  const [values, setValues] = useState<FormValues>(() => valuesFrom(current));
  const [state, action, pending] = useActionState<ConstraintsFormState, FormData>(
    reviewConstraints,
    INITIAL_CONSTRAINTS_STATE,
  );
  const router = useRouter();

  useEffect(() => {
    if (state.saved) router.refresh();
  }, [state.saved, router]);

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((previous) => ({ ...previous, [key]: value }));
  }

  return (
    <form action={action} className="space-y-8">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Restricciones</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} · actualizado el {current.updated_at}
        </p>
      </header>

      <section className="space-y-2">
        <h2 className={sectionTitleClass}>Restricciones básicas</h2>
        <label className={labelClass}>
          <span className={captionClass}>Separadas por comas</span>
          <input
            type="text"
            name="hard_constraints"
            value={values.hardConstraints}
            onChange={(e) => set("hardConstraints", e.target.value)}
            className={inputClass}
          />
        </label>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Lo que se sabe hoy</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            <span className={captionClass}>Momento</span>
            <input
              type="text"
              name="timing"
              value={values.timing}
              onChange={(e) => set("timing", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Suelo salarial en España (EUR)</span>
            <input
              type="number"
              name="spain_salary_floor_gross_eur"
              value={values.spainSalaryFloorGrossEur}
              onChange={(e) => set("spainSalaryFloorGrossEur", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Reubicación</span>
            <input
              type="text"
              name="relocation"
              value={values.relocation}
              onChange={(e) => set("relocation", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Patrocinio de visado</span>
            <input
              type="text"
              name="ckc_visa_sponsorship"
              value={values.visaSponsorship}
              onChange={(e) => set("visaSponsorship", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="eu_work_authorization"
            checked={values.euWorkAuthorization}
            onChange={(e) => set("euWorkAuthorization", e.target.checked)}
          />
          Autorización de trabajo en la UE
        </label>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Política sectorial</h2>
        <label className={labelClass}>
          <span className={captionClass}>Sectores excluidos, separados por comas</span>
          <input
            type="text"
            name="excluded_industries"
            value={values.excludedIndustries}
            onChange={(e) => set("excludedIndustries", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Regla</span>
          <textarea
            name="sector_rule"
            rows={2}
            value={values.sectorRule}
            onChange={(e) => set("sectorRule", e.target.value)}
            className={textareaClass}
          />
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Nota</span>
          <textarea
            name="sector_note"
            rows={2}
            value={values.sectorNote}
            onChange={(e) => set("sectorNote", e.target.value)}
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-3">
        <h2 className={sectionTitleClass}>Condiciones descalificantes</h2>
        <DisqualifyingConditionsEditor
          rows={values.disqualifyingConditions}
          onChange={(rows) => set("disqualifyingConditions", rows)}
        />
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Condiciones aceptadas</h2>
        <label className={labelClass}>
          <span className={captionClass}>Guardias y turnos</span>
          <input
            type="text"
            name="on_call_and_shift_work"
            value={values.onCallAndShiftWork}
            onChange={(e) => set("onCallAndShiftWork", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Alta intensidad</span>
          <textarea
            name="high_intensity"
            rows={2}
            value={values.highIntensity}
            onChange={(e) => set("highIntensity", e.target.value)}
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-2">
        <h2 className={sectionTitleClass}>Decisiones pendientes</h2>
        <label className={labelClass}>
          <span className={captionClass}>Separadas por comas</span>
          <input
            type="text"
            name="pending_decisions"
            value={values.pendingDecisions}
            onChange={(e) => set("pendingDecisions", e.target.value)}
            className={inputClass}
          />
        </label>
      </section>

      <section className="space-y-3">
        <h2 className={sectionTitleClass}>Decisiones sustituidas</h2>
        <SupersededDecisionsEditor
          rows={values.supersededDecisions}
          onChange={(rows) => set("supersededDecisions", rows)}
        />
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
