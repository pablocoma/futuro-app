"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { Objectives } from "@/lib/api";
import { DECLARABLE_ROLE_FAMILIES, ROLE_FAMILY_LABELS } from "@/lib/labels";

import { reviewObjectives, type ObjectivesFormState } from "./actions";

const INITIAL_OBJECTIVES_STATE: ObjectivesFormState = {
  error: null,
  diff: null,
  saved: false,
  commitSha: null,
};

type FamilyChoice = "none" | "core" | "exploratory";

type FormValues = {
  targetYear: string;
  tenureMin: string;
  tenureMax: string;
  urgency: string;
  statement: string;
  successDimensions: string;
  families: Record<string, FamilyChoice>;
};

function familyChoice(current: Objectives, family: string): FamilyChoice {
  if (current.role_families.core.includes(family)) return "core";
  if (current.role_families.exploratory.includes(family)) return "exploratory";
  return "none";
}

function valuesFrom(current: Objectives): FormValues {
  const families: Record<string, FamilyChoice> = {};
  for (const family of DECLARABLE_ROLE_FAMILIES) {
    families[family] = familyChoice(current, family);
  }
  return {
    targetYear: String(current.transition.target_year),
    tenureMin: String(current.transition.expected_tenure_years[0]),
    tenureMax: String(current.transition.expected_tenure_years[1]),
    urgency: current.transition.urgency,
    statement: current.primary_objective.statement,
    successDimensions: current.success_dimensions.join(", "),
    families,
  };
}

/**
 * Todos los campos son controlados a propósito, no `defaultValue`: React
 * resetea los campos no controlados de un `<form action={...}>` en cuanto
 * la acción del servidor termina -pensado para un formulario que se limpia
 * solo tras publicar un comentario-, y aquí es justo lo contrario de lo
 * que hace falta: lo que se ve en el diff tiene que seguir en el formulario
 * cuando se pulsa «Confirmar y guardar» a continuación. Se descubrió
 * viendo que el commit escribía siempre el valor original, sin usar nunca
 * lo editado.
 */
export function ObjectivesForm({ current }: { current: Objectives }) {
  const [values, setValues] = useState<FormValues>(() => valuesFrom(current));
  const [state, action, pending] = useActionState<ObjectivesFormState, FormData>(
    reviewObjectives,
    INITIAL_OBJECTIVES_STATE,
  );
  const router = useRouter();

  // Tras un commit de verdad, la pantalla vuelve a pedirse al servidor:
  // es lo que hace que "versión" y "última actualización" no mientan.
  useEffect(() => {
    if (state.saved) router.refresh();
  }, [state.saved, router]);

  function setFamily(family: string, choice: FamilyChoice) {
    setValues((previous) => ({
      ...previous,
      families: { ...previous.families, [family]: choice },
    }));
  }

  return (
    <form action={action} className="space-y-8">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Objetivos</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} · actualizado el {current.updated_at}
        </p>
      </header>

      <section className="space-y-4">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink3">
          Transición
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="block text-ink2">Año objetivo</span>
            <input
              type="number"
              name="target_year"
              value={values.targetYear}
              onChange={(e) =>
                setValues((v) => ({ ...v, targetYear: e.target.value }))
              }
              className="w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-ink2">Permanencia mínima (años)</span>
            <input
              type="number"
              name="tenure_min"
              value={values.tenureMin}
              onChange={(e) =>
                setValues((v) => ({ ...v, tenureMin: e.target.value }))
              }
              className="w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="block text-ink2">Permanencia máxima (años)</span>
            <input
              type="number"
              name="tenure_max"
              value={values.tenureMax}
              onChange={(e) =>
                setValues((v) => ({ ...v, tenureMax: e.target.value }))
              }
              className="w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5"
            />
          </label>
        </div>
        <label className="block space-y-1 text-sm">
          <span className="block text-ink2">Urgencia</span>
          <input
            type="text"
            name="urgency"
            value={values.urgency}
            onChange={(e) => setValues((v) => ({ ...v, urgency: e.target.value }))}
            className="w-full max-w-xs rounded-md border border-white/15 bg-transparent px-3 py-1.5"
          />
        </label>
      </section>

      <section className="space-y-2">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink3">
          Objetivo principal
        </h2>
        <label className="block space-y-1 text-sm">
          <span className="block text-ink2">Declaración</span>
          <textarea
            name="statement"
            rows={3}
            value={values.statement}
            onChange={(e) => setValues((v) => ({ ...v, statement: e.target.value }))}
            className="w-full rounded-md border border-white/15 bg-transparent px-3 py-2"
          />
        </label>
      </section>

      <section className="space-y-2">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink3">
          Dimensiones de éxito
        </h2>
        <label className="block space-y-1 text-sm">
          <span className="block text-ink2">
            Separadas por comas, en el orden en que importan
          </span>
          <input
            type="text"
            name="success_dimensions"
            value={values.successDimensions}
            onChange={(e) =>
              setValues((v) => ({ ...v, successDimensions: e.target.value }))
            }
            className="w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5"
          />
        </label>
      </section>

      <section className="space-y-3">
        <h2 className="font-mono text-xs uppercase tracking-widest text-ink3">
          Familias de rol
        </h2>
        <p className="text-sm text-ink2">
          «Core» son las que cuentan como el objetivo; «exploratoria» es la
          única que hoy admite el modelo de scoring fuera de ese núcleo.
        </p>
        <div className="divide-y divide-white/5 rounded-lg border border-white/10">
          {DECLARABLE_ROLE_FAMILIES.map((family) => (
            <fieldset
              key={family}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
            >
              <legend className="sr-only">{ROLE_FAMILY_LABELS[family]}</legend>
              <span className="text-sm">{ROLE_FAMILY_LABELS[family]}</span>
              <div className="flex gap-4 font-mono text-xs uppercase tracking-widest text-ink2">
                {(["none", "core", "exploratory"] as const).map((option) => (
                  <label key={option} className="flex items-center gap-1.5">
                    <input
                      type="radio"
                      name={`family_${family}`}
                      value={option}
                      checked={values.families[family] === option}
                      onChange={() => setFamily(family, option)}
                    />
                    {option === "none"
                      ? "ninguna"
                      : option === "core"
                        ? "core"
                        : "exploratoria"}
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
      </section>

      {state.error && <p className="font-mono text-sm text-neg">▲ {state.error}</p>}

      {state.diff !== null && (
        <section className="space-y-2">
          <h2 className="font-mono text-xs uppercase tracking-widest text-ink3">
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
