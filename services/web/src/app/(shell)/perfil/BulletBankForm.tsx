"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { Bullet, BulletBank, BulletEdit, BulletEvidenceStatus, BulletCvUsage } from "@/lib/api";
import { BULLET_CV_USAGE_LABELS, BULLET_EVIDENCE_STATUS_LABELS } from "@/lib/labels";

import { reviewBulletBank, type BulletBankFormState } from "./actions";

const INITIAL_BULLET_BANK_STATE: BulletBankFormState = {
  error: null,
  diff: null,
  saved: false,
  commitSha: null,
};

const inputClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5 text-sm";
const textareaClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-2 text-sm";
const selectClass = inputClass;
const captionClass = "block text-ink2";
const sectionTitleClass = "font-mono text-xs uppercase tracking-widest text-ink3";

function toEdit(bullet: Bullet): BulletEdit {
  return {
    bullet_id: bullet.bullet_id,
    text_en: bullet.text_en,
    evidence_status: bullet.evidence_status,
    cv_usage: bullet.cv_usage,
  };
}

/**
 * Solo `text_en`, `evidence_status` y `cv_usage` son editables por fila
 * -alcance confirmado con Pablo el 2026-09-07-. `bullet_id` es de solo
 * lectura en una fila existente, mismo motivo que en
 * `DisqualifyingConditionsEditor`: el backend casa por `bullet_id`, y
 * editarlo libremente crearía una fila nueva en vez de renombrar nada.
 * El resto de metadatos de cada bullet (proyecto, ángulo, variantes de rol,
 * confidencialidad) se enseña de solo lectura junto a la fila: esta
 * rebanada no los gestiona.
 */
function BulletRowEditor({
  bullets,
  original,
  onChange,
}: {
  bullets: BulletEdit[];
  original: Record<string, Bullet>;
  onChange: (rows: BulletEdit[]) => void;
}) {
  function update(index: number, changes: Partial<BulletEdit>) {
    onChange(bullets.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  }

  return (
    <div className="space-y-3">
      <input type="hidden" name="bullets_json" value={JSON.stringify(bullets)} />
      <div className="divide-y divide-white/5 rounded-lg border border-white/10">
        {bullets.map((row, index) => {
          const meta = original[row.bullet_id];
          return (
            <div key={row.bullet_id} className="space-y-2 px-4 py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-mono text-xs text-ink3">{row.bullet_id}</p>
                {meta && (
                  <p className="text-xs text-ink3">
                    {meta.bullet_type}
                    {meta.project_id ? ` · ${meta.project_id}` : ""}
                    {meta.role_variants.length > 0
                      ? ` · ${meta.role_variants.join(", ")}`
                      : ""}
                  </p>
                )}
              </div>
              <textarea
                rows={2}
                aria-label={`Texto de ${row.bullet_id}`}
                value={row.text_en}
                onChange={(e) => update(index, { text_en: e.target.value })}
                className={textareaClass}
              />
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className={captionClass}>Estado de la evidencia</span>
                  <select
                    aria-label={`Estado de la evidencia de ${row.bullet_id}`}
                    value={row.evidence_status}
                    onChange={(e) =>
                      update(index, {
                        evidence_status: e.target.value as BulletEvidenceStatus,
                      })
                    }
                    className={selectClass}
                  >
                    {Object.entries(BULLET_EVIDENCE_STATUS_LABELS).map(
                      ([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className={captionClass}>Uso en CV</span>
                  <select
                    aria-label={`Uso en CV de ${row.bullet_id}`}
                    value={row.cv_usage}
                    onChange={(e) =>
                      update(index, { cv_usage: e.target.value as BulletCvUsage })
                    }
                    className={selectClass}
                  >
                    {Object.entries(BULLET_CV_USAGE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** El alta: sin borrado en esta rebanada, así que solo hace falta un
 * formulario de "añadir". Los campos que el fichero exige pero el
 * formulario no gestiona -proyecto, ángulo, confidencialidad- los rellena
 * el backend con valores seguros, sin fabricar una confirmación que nadie
 * ha dado. */
function AddBulletEditor({
  existingIds,
  onAdd,
}: {
  existingIds: string[];
  onAdd: (row: BulletEdit) => void;
}) {
  const [bulletId, setBulletId] = useState("");
  const [textEn, setTextEn] = useState("");
  const [evidenceStatus, setEvidenceStatus] =
    useState<BulletEvidenceStatus>("candidate");
  const [cvUsage, setCvUsage] = useState<BulletCvUsage>("blocked");

  function add() {
    const id = bulletId.trim();
    const text = textEn.trim();
    if (!id || !text || existingIds.includes(id)) return;
    onAdd({ bullet_id: id, text_en: text, evidence_status: evidenceStatus, cv_usage: cvUsage });
    setBulletId("");
    setTextEn("");
    setEvidenceStatus("candidate");
    setCvUsage("blocked");
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed border-white/15 p-4">
      <p className={captionClass}>Añadir un bullet nuevo</p>
      <input
        type="text"
        placeholder="identificador"
        value={bulletId}
        onChange={(e) => setBulletId(e.target.value)}
        className={inputClass}
      />
      <textarea
        rows={2}
        placeholder="texto"
        value={textEn}
        onChange={(e) => setTextEn(e.target.value)}
        className={textareaClass}
      />
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <select
          value={evidenceStatus}
          onChange={(e) => setEvidenceStatus(e.target.value as BulletEvidenceStatus)}
          className={selectClass}
        >
          {Object.entries(BULLET_EVIDENCE_STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          value={cvUsage}
          onChange={(e) => setCvUsage(e.target.value as BulletCvUsage)}
          className={selectClass}
        >
          {Object.entries(BULLET_CV_USAGE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <button type="button" onClick={add} className="btn-link">
        + Añadir bullet
      </button>
    </div>
  );
}

export function BulletBankForm({ current }: { current: BulletBank }) {
  const [bullets, setBullets] = useState<BulletEdit[]>(() =>
    current.bullets.map(toEdit),
  );
  const original = Object.fromEntries(current.bullets.map((b) => [b.bullet_id, b]));
  const [state, action, pending] = useActionState<BulletBankFormState, FormData>(
    reviewBulletBank,
    INITIAL_BULLET_BANK_STATE,
  );
  const router = useRouter();

  useEffect(() => {
    if (state.saved) router.refresh();
  }, [state.saved, router]);

  const statusClaimsNote = current.policy.status_claims_confirmed_2026_08_14;

  return (
    <form action={action} className="space-y-8">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Banco de bullets</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} · actualizado el {current.updated_at}
        </p>
      </header>

      {typeof statusClaimsNote === "string" && (
        <section className="space-y-2">
          <h2 className={sectionTitleClass}>
            Revisión de redacción de estado (2026-08-14)
          </h2>
          <p className="rounded-lg border border-white/10 bg-white/[0.02] p-4 text-sm text-ink2">
            {statusClaimsNote}
          </p>
        </section>
      )}

      <section className="space-y-3">
        <h2 className={sectionTitleClass}>Bullets</h2>
        <BulletRowEditor bullets={bullets} original={original} onChange={setBullets} />
        <AddBulletEditor
          existingIds={bullets.map((b) => b.bullet_id)}
          onAdd={(row) => setBullets((rows) => [...rows, row])}
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
