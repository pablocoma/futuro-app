"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { RoleVariantContent, SkillRow, VariantContent } from "@/lib/api";

import { reviewRoleVariants, type RoleVariantsFormState } from "./actions";

const INITIAL_ROLE_VARIANTS_STATE: RoleVariantsFormState = {
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

/** Filas de largo variable, sin identificador estable: se editan y se
 * quitan por posición, mismo patrón que `SupersededDecisionsEditor`. */
function SkillsEditor({
  rows,
  onChange,
}: {
  rows: SkillRow[];
  onChange: (rows: SkillRow[]) => void;
}) {
  function update(index: number, changes: Partial<SkillRow>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  }

  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function addRow() {
    onChange([...rows, { label: "", value: "" }]);
  }

  return (
    <div className="space-y-2">
      {rows.map((row, index) => (
        <div key={index} className="flex flex-wrap items-start gap-2">
          <input
            type="text"
            placeholder="etiqueta"
            value={row.label}
            onChange={(e) => update(index, { label: e.target.value })}
            className={`${inputClass} sm:w-40`}
          />
          <input
            type="text"
            placeholder="valor"
            value={row.value}
            onChange={(e) => update(index, { value: e.target.value })}
            className={`${inputClass} flex-1`}
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

function VariantEditor({
  variantId,
  content,
  onChange,
}: {
  variantId: string;
  content: VariantContent;
  onChange: (content: VariantContent) => void;
}) {
  return (
    <div className="space-y-4 rounded-lg border border-white/10 p-4">
      <p className="font-mono text-xs text-ink3">{variantId}</p>
      <label className="block space-y-1 text-sm">
        <span className={captionClass}>Nombre para mostrar</span>
        <input
          type="text"
          aria-label={`Nombre para mostrar de ${variantId}`}
          value={content.display_name}
          onChange={(e) => onChange({ ...content, display_name: e.target.value })}
          className={inputClass}
        />
      </label>
      <label className="block space-y-1 text-sm">
        <span className={captionClass}>Cuándo usarla</span>
        <textarea
          rows={2}
          aria-label={`Cuándo usarla de ${variantId}`}
          value={content.use_when}
          onChange={(e) => onChange({ ...content, use_when: e.target.value })}
          className={textareaClass}
        />
      </label>
      <label className="block space-y-1 text-sm">
        <span className={captionClass}>Perfil</span>
        <textarea
          rows={3}
          aria-label={`Perfil de ${variantId}`}
          value={content.profile}
          onChange={(e) => onChange({ ...content, profile: e.target.value })}
          className={textareaClass}
        />
      </label>
      <div className="space-y-1 text-sm">
        <span className={captionClass}>Habilidades</span>
        <SkillsEditor
          rows={content.skills}
          onChange={(skills) => onChange({ ...content, skills })}
        />
      </div>
    </div>
  );
}

/**
 * Las claves de `variants` son fijas -esta rebanada no da de alta ni de
 * baja variantes, decidido con Pablo el 2026-09-07-: se recorren en el
 * orden en que ya vienen del backend, sin ofrecer ningún camino para
 * añadir o quitar una.
 */
export function RoleVariantsForm({ current }: { current: RoleVariantContent }) {
  const [variants, setVariants] = useState<Record<string, VariantContent>>(
    () => current.variants,
  );
  const [state, action, pending] = useActionState<RoleVariantsFormState, FormData>(
    reviewRoleVariants,
    INITIAL_ROLE_VARIANTS_STATE,
  );
  const router = useRouter();

  useEffect(() => {
    if (state.saved) router.refresh();
  }, [state.saved, router]);

  return (
    <form action={action} className="space-y-8">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Variantes de rol</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} · actualizado el {current.updated_at}
        </p>
      </header>

      <input type="hidden" name="variants_json" value={JSON.stringify(variants)} />

      <section className="space-y-4">
        {Object.entries(variants).map(([variantId, content]) => (
          <VariantEditor
            key={variantId}
            variantId={variantId}
            content={content}
            onChange={(next) =>
              setVariants((previous) => ({ ...previous, [variantId]: next }))
            }
          />
        ))}
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
