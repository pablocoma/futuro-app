"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { Preferences } from "@/lib/api";

import { reviewPreferences, type PreferencesFormState } from "./actions";

const INITIAL_PREFERENCES_STATE: PreferencesFormState = {
  error: null,
  diff: null,
  saved: false,
  commitSha: null,
};

type FormValues = {
  preference: string;
  avoidNarrowSpecialization: boolean;
  clientFacing: string;
  programming: string;
  travel: string;
  willingToAcceptHighIntensity: boolean;
  durationMin: string;
  durationMax: string;
  condition: string;
  onsite: string;
  hybrid: string;
  remote: string;
  euPassport: boolean;
  visaSponsorship: string;
  countries: string;
  madridAdvantage: string;
  spainMinimumGrossEur: string;
  currentMadridGrossEur: string;
  currentMadridNetMonthlyEur: string;
  currentMadridPaymentsPerYear: string;
  livingCostsMin: string;
  livingCostsMax: string;
  currentAnnualSavingsEur: string;
  savingsBaselineNote: string;
  abroadHousingAssumption: string;
  outsideMadridRule: string;
  internationalTargets: string;
  spanish: string;
  englishInterview: string;
  evidence: string;
  cvPolicy: string;
  contributionGranularity: string;
  avoidInternalTaskBreakdown: boolean;
  acceptableEvidence: string;
  cvImplication: string;
};

function valuesFrom(current: Preferences): FormValues {
  return {
    preference: current.work_content.preference,
    avoidNarrowSpecialization: current.work_content.avoid_narrow_specialization,
    clientFacing: current.work_content.client_facing,
    programming: current.work_content.programming,
    travel: current.work_content.travel,
    willingToAcceptHighIntensity:
      current.work_intensity.willing_to_accept_high_intensity,
    durationMin: String(current.work_intensity.intended_duration_years[0]),
    durationMax: String(current.work_intensity.intended_duration_years[1]),
    condition: current.work_intensity.condition,
    onsite: current.work_mode.onsite,
    hybrid: current.work_mode.hybrid,
    remote: current.work_mode.remote,
    euPassport: current.geography.eu_passport,
    visaSponsorship: current.geography.visa_sponsorship,
    countries: current.geography.countries,
    madridAdvantage: current.geography.madrid_advantage,
    spainMinimumGrossEur: String(current.compensation.spain_minimum_gross_eur),
    currentMadridGrossEur: String(current.compensation.current_madrid_gross_eur),
    currentMadridNetMonthlyEur: String(
      current.compensation.current_madrid_net_monthly_eur,
    ),
    currentMadridPaymentsPerYear: String(
      current.compensation.current_madrid_payments_per_year,
    ),
    livingCostsMin: String(current.compensation.current_living_costs_monthly_eur[0]),
    livingCostsMax: String(current.compensation.current_living_costs_monthly_eur[1]),
    currentAnnualSavingsEur: String(current.compensation.current_annual_savings_eur),
    savingsBaselineNote: current.compensation.savings_baseline_note,
    abroadHousingAssumption: current.compensation.abroad_housing_assumption,
    outsideMadridRule: current.compensation.outside_madrid_rule,
    internationalTargets: current.compensation.international_targets,
    spanish: current.language.spanish,
    englishInterview: current.language.english_interview,
    evidence: current.language.evidence.join(", "),
    cvPolicy: current.language.cv_policy,
    contributionGranularity:
      current.professional_project_documentation.contribution_granularity,
    avoidInternalTaskBreakdown:
      current.professional_project_documentation.avoid_internal_task_breakdown,
    acceptableEvidence: current.professional_project_documentation.acceptable_evidence,
    cvImplication: current.professional_project_documentation.cv_implication,
  };
}

const inputClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5 text-sm";
const textareaClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-2 text-sm";
const labelClass = "block space-y-1 text-sm";
const captionClass = "block text-ink2";
const sectionTitleClass = "font-mono text-xs uppercase tracking-widest text-ink3";

/** Campos controlados, no `defaultValue`: mismo hallazgo que
 * `ObjectivesForm` -React resetea los no controlados al terminar la
 * acción del servidor, y aquí el diff tiene que sobrevivir hasta
 * «Confirmar y guardar»-. */
export function PreferencesForm({ current }: { current: Preferences }) {
  const [values, setValues] = useState<FormValues>(() => valuesFrom(current));
  const [state, action, pending] = useActionState<PreferencesFormState, FormData>(
    reviewPreferences,
    INITIAL_PREFERENCES_STATE,
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
        <h2 className="text-2xl font-semibold tracking-tight">Preferencias</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} · actualizado el {current.updated_at}
        </p>
      </header>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Contenido del trabajo</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            <span className={captionClass}>Preferencia</span>
            <input
              type="text"
              name="preference"
              value={values.preference}
              onChange={(e) => set("preference", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Cara al cliente</span>
            <input
              type="text"
              name="client_facing"
              value={values.clientFacing}
              onChange={(e) => set("clientFacing", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Programación</span>
            <input
              type="text"
              name="programming"
              value={values.programming}
              onChange={(e) => set("programming", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Viaje</span>
            <input
              type="text"
              name="travel"
              value={values.travel}
              onChange={(e) => set("travel", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="avoid_narrow_specialization"
            checked={values.avoidNarrowSpecialization}
            onChange={(e) => set("avoidNarrowSpecialization", e.target.checked)}
          />
          Evitar especialización estrecha
        </label>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Intensidad del trabajo</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="willing_to_accept_high_intensity"
            checked={values.willingToAcceptHighIntensity}
            onChange={(e) => set("willingToAcceptHighIntensity", e.target.checked)}
          />
          Dispuesto a aceptar alta intensidad
        </label>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            <span className={captionClass}>Duración mínima (años)</span>
            <input
              type="number"
              name="duration_min"
              value={values.durationMin}
              onChange={(e) => set("durationMin", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Duración máxima (años)</span>
            <input
              type="number"
              name="duration_max"
              value={values.durationMax}
              onChange={(e) => set("durationMax", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <label className={labelClass}>
          <span className={captionClass}>Condición</span>
          <textarea
            name="condition"
            rows={2}
            value={values.condition}
            onChange={(e) => set("condition", e.target.value)}
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Modalidad de trabajo</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className={labelClass}>
            <span className={captionClass}>Presencial</span>
            <input
              type="text"
              name="onsite"
              value={values.onsite}
              onChange={(e) => set("onsite", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Híbrida</span>
            <input
              type="text"
              name="hybrid"
              value={values.hybrid}
              onChange={(e) => set("hybrid", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Remota</span>
            <input
              type="text"
              name="remote"
              value={values.remote}
              onChange={(e) => set("remote", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Geografía</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="eu_passport"
            checked={values.euPassport}
            onChange={(e) => set("euPassport", e.target.checked)}
          />
          Pasaporte UE
        </label>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className={labelClass}>
            <span className={captionClass}>Patrocinio de visado</span>
            <input
              type="text"
              name="visa_sponsorship"
              value={values.visaSponsorship}
              onChange={(e) => set("visaSponsorship", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Países</span>
            <input
              type="text"
              name="countries"
              value={values.countries}
              onChange={(e) => set("countries", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Ventaja de Madrid</span>
            <input
              type="text"
              name="madrid_advantage"
              value={values.madridAdvantage}
              onChange={(e) => set("madridAdvantage", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Compensación</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            <span className={captionClass}>Mínimo bruto en España (EUR)</span>
            <input
              type="number"
              name="spain_minimum_gross_eur"
              value={values.spainMinimumGrossEur}
              onChange={(e) => set("spainMinimumGrossEur", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Bruto actual en Madrid (EUR)</span>
            <input
              type="number"
              name="current_madrid_gross_eur"
              value={values.currentMadridGrossEur}
              onChange={(e) => set("currentMadridGrossEur", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Neto mensual actual en Madrid (EUR)</span>
            <input
              type="number"
              name="current_madrid_net_monthly_eur"
              value={values.currentMadridNetMonthlyEur}
              onChange={(e) => set("currentMadridNetMonthlyEur", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Pagas al año</span>
            <input
              type="number"
              name="current_madrid_payments_per_year"
              value={values.currentMadridPaymentsPerYear}
              onChange={(e) => set("currentMadridPaymentsPerYear", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Coste de vida mínimo mensual (EUR)</span>
            <input
              type="number"
              name="living_costs_min"
              value={values.livingCostsMin}
              onChange={(e) => set("livingCostsMin", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Coste de vida máximo mensual (EUR)</span>
            <input
              type="number"
              name="living_costs_max"
              value={values.livingCostsMax}
              onChange={(e) => set("livingCostsMax", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Ahorro anual actual (EUR)</span>
            <input
              type="number"
              name="current_annual_savings_eur"
              value={values.currentAnnualSavingsEur}
              onChange={(e) => set("currentAnnualSavingsEur", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Objetivos internacionales</span>
            <input
              type="text"
              name="international_targets"
              value={values.internationalTargets}
              onChange={(e) => set("internationalTargets", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <label className={labelClass}>
          <span className={captionClass}>Referencia de ahorro</span>
          <textarea
            name="savings_baseline_note"
            rows={2}
            value={values.savingsBaselineNote}
            onChange={(e) => set("savingsBaselineNote", e.target.value)}
            className={textareaClass}
          />
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Supuesto de vivienda fuera de Madrid</span>
          <textarea
            name="abroad_housing_assumption"
            rows={2}
            value={values.abroadHousingAssumption}
            onChange={(e) => set("abroadHousingAssumption", e.target.value)}
            className={textareaClass}
          />
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Regla fuera de Madrid</span>
          <textarea
            name="outside_madrid_rule"
            rows={2}
            value={values.outsideMadridRule}
            onChange={(e) => set("outsideMadridRule", e.target.value)}
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Idioma</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            <span className={captionClass}>Español</span>
            <input
              type="text"
              name="spanish"
              value={values.spanish}
              onChange={(e) => set("spanish", e.target.value)}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            <span className={captionClass}>Inglés en entrevista</span>
            <input
              type="text"
              name="english_interview"
              value={values.englishInterview}
              onChange={(e) => set("englishInterview", e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
        <label className={labelClass}>
          <span className={captionClass}>Evidencia, separada por comas</span>
          <input
            type="text"
            name="evidence"
            value={values.evidence}
            onChange={(e) => set("evidence", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Política para el CV</span>
          <textarea
            name="cv_policy"
            rows={2}
            value={values.cvPolicy}
            onChange={(e) => set("cvPolicy", e.target.value)}
            className={textareaClass}
          />
        </label>
      </section>

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Documentación de proyectos</h2>
        <label className={labelClass}>
          <span className={captionClass}>Granularidad de contribución</span>
          <input
            type="text"
            name="contribution_granularity"
            value={values.contributionGranularity}
            onChange={(e) => set("contributionGranularity", e.target.value)}
            className={inputClass}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="avoid_internal_task_breakdown"
            checked={values.avoidInternalTaskBreakdown}
            onChange={(e) => set("avoidInternalTaskBreakdown", e.target.checked)}
          />
          Evitar desglose interno de tareas
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Evidencia aceptable</span>
          <textarea
            name="acceptable_evidence"
            rows={2}
            value={values.acceptableEvidence}
            onChange={(e) => set("acceptableEvidence", e.target.value)}
            className={textareaClass}
          />
        </label>
        <label className={labelClass}>
          <span className={captionClass}>Implicación para el CV</span>
          <textarea
            name="cv_implication"
            rows={2}
            value={values.cvImplication}
            onChange={(e) => set("cvImplication", e.target.value)}
            className={textareaClass}
          />
        </label>
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
