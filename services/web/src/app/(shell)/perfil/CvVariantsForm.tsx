"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { BaseVariant, BaseVariantEdit, CvVariants } from "@/lib/api";

import { reviewCvVariants, type CvVariantsFormState } from "./actions";

const INITIAL_CV_VARIANTS_STATE: CvVariantsFormState = {
  error: null,
  diff: null,
  saved: false,
  commitSha: null,
};

const inputClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5 text-sm";
const captionClass = "block text-ink2";
const sectionTitleClass = "font-mono text-xs uppercase tracking-widest text-ink3";

function splitCommaList(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function toEdit(variant: BaseVariant): BaseVariantEdit {
  return {
    target_roles: variant.target_roles,
    emphasis: variant.emphasis,
    professional_project_priority: variant.professional_project_priority,
    public_project_priority: variant.public_project_priority,
    candidate_bullet_priority: variant.candidate_bullet_priority,
  };
}

const EDITABLE_FIELDS: { key: keyof BaseVariantEdit; label: string }[] = [
  { key: "target_roles", label: "Roles objetivo" },
  { key: "emphasis", label: "Énfasis" },
  {
    key: "professional_project_priority",
    label: "Prioridad de proyectos profesionales",
  },
  { key: "public_project_priority", label: "Prioridad de proyectos públicos" },
  { key: "candidate_bullet_priority", label: "Prioridad de bullets candidatos" },
];

/**
 * El núcleo editable de una variante activa: cinco listas de
 * identificadores, como texto separado por comas -mismo criterio que
 * `hard_constraints`/`pending_decisions`-. Los campos atípicos
 * (`display_name`, `target_role_condition`, `note`, `exclusive_evidence`)
 * se enseñan de solo lectura junto al núcleo: decidido con Pablo el
 * 2026-09-07, esta rebanada no los gestiona.
 */
function VariantEditor({
  variantId,
  original,
  edit,
  onChange,
}: {
  variantId: string;
  original: BaseVariant;
  edit: BaseVariantEdit;
  onChange: (edit: BaseVariantEdit) => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-white/10 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-mono text-xs text-ink3">{variantId}</p>
        {original.display_name && (
          <p className="text-xs text-ink3">{original.display_name}</p>
        )}
      </div>
      {EDITABLE_FIELDS.map(({ key, label }) => (
        <label key={key} className="block space-y-1 text-sm">
          <span className={captionClass}>{label}</span>
          <input
            type="text"
            aria-label={`${label} de ${variantId}`}
            value={edit[key].join(", ")}
            onChange={(e) =>
              onChange({ ...edit, [key]: splitCommaList(e.target.value) })
            }
            className={inputClass}
          />
        </label>
      ))}
      {(original.note ||
        original.target_role_condition ||
        original.exclusive_evidence.length > 0) && (
        <div className="space-y-1 border-t border-white/5 pt-2 text-xs text-ink3">
          {original.note && <p>Nota: {original.note}</p>}
          {original.target_role_condition && (
            <p>Condición de rol objetivo: {original.target_role_condition}</p>
          )}
          {original.exclusive_evidence.length > 0 && (
            <p>Evidencia exclusiva: {original.exclusive_evidence.join(", ")}</p>
          )}
        </div>
      )}
    </div>
  );
}

/** Una variante con `status` -`quant_exploratory` en el repositorio real-
 * no tiene las listas de prioridad y no tiene contraparte en
 * `role_variant_content.yaml`: decidido con Pablo el 2026-09-07, de solo
 * lectura y fuera del formulario. */
function BlockedVariant({
  variantId,
  variant,
}: {
  variantId: string;
  variant: BaseVariant;
}) {
  return (
    <div className="space-y-1 rounded-lg border border-dashed border-white/15 p-4 text-sm text-ink3">
      <p className="font-mono text-xs">{variantId}</p>
      <p>Estado: {variant.status}</p>
      {variant.target_roles.length > 0 && (
        <p>Roles objetivo: {variant.target_roles.join(", ")}</p>
      )}
    </div>
  );
}

export function CvVariantsForm({ current }: { current: CvVariants }) {
  const activeEntries = Object.entries(current.base_variants).filter(
    ([, variant]) => variant.status === null,
  );
  const blockedEntries = Object.entries(current.base_variants).filter(
    ([, variant]) => variant.status !== null,
  );

  const [edits, setEdits] = useState<Record<string, BaseVariantEdit>>(() =>
    Object.fromEntries(activeEntries.map(([id, variant]) => [id, toEdit(variant)])),
  );
  const [state, action, pending] = useActionState<CvVariantsFormState, FormData>(
    reviewCvVariants,
    INITIAL_CV_VARIANTS_STATE,
  );
  const router = useRouter();

  useEffect(() => {
    if (state.saved) router.refresh();
  }, [state.saved, router]);

  return (
    <form action={action} className="space-y-8">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Variantes de CV</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} · actualizado el {current.updated_at}
        </p>
      </header>

      <input type="hidden" name="base_variants_json" value={JSON.stringify(edits)} />

      <section className="space-y-4">
        <h2 className={sectionTitleClass}>Variantes activas</h2>
        {activeEntries.map(([variantId, variant]) => (
          <VariantEditor
            key={variantId}
            variantId={variantId}
            original={variant}
            edit={edits[variantId]}
            onChange={(next) =>
              setEdits((previous) => ({ ...previous, [variantId]: next }))
            }
          />
        ))}
      </section>

      {blockedEntries.length > 0 && (
        <section className="space-y-3">
          <h2 className={sectionTitleClass}>Bloqueadas, de solo lectura</h2>
          {blockedEntries.map(([variantId, variant]) => (
            <BlockedVariant key={variantId} variantId={variantId} variant={variant} />
          ))}
        </section>
      )}

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
