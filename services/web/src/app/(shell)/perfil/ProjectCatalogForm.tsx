"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { Project, ProjectCatalog, ProjectCvUsage, ProjectEdit } from "@/lib/api";
import { BULLET_EVIDENCE_STATUS_LABELS, PROJECT_CV_USAGE_LABELS } from "@/lib/labels";

import { reviewProjectCatalog, type ProjectCatalogFormState } from "./actions";

const INITIAL_PROJECT_CATALOG_STATE: ProjectCatalogFormState = {
  error: null,
  diff: null,
  saved: false,
  commitSha: null,
};

const inputClass =
  "w-full rounded-md border border-white/15 bg-transparent px-3 py-1.5 text-sm";
const selectClass = inputClass;
const captionClass = "block text-ink2";
const sectionTitleClass = "font-mono text-xs uppercase tracking-widest text-ink3";

function toEdit(project: Project): ProjectEdit {
  return {
    project_id: project.project_id,
    safe_name: project.safe_name,
    evidence_status: project.evidence_status,
    cv_usage: project.cv_usage,
    interview_usage: project.interview_usage,
    pending_confirmations: project.pending_confirmations,
  };
}

/**
 * Sin alta ni baja en esta rebanada -decidido con Pablo el 2026-09-07-:
 * `project_id` casa cada fila, igual que `bullet_id` en M2. El resto de
 * cada proyecto -`source_type`, `confidentiality`, `canonical_source`,
 * `role_family_fit`, `professional_value_signals`- se enseña de solo
 * lectura junto a la fila: esta rebanada no lo gestiona.
 */
function ProjectRowEditor({
  projects,
  original,
  onChange,
}: {
  projects: ProjectEdit[];
  original: Record<string, Project>;
  onChange: (rows: ProjectEdit[]) => void;
}) {
  function update(index: number, changes: Partial<ProjectEdit>) {
    onChange(projects.map((row, i) => (i === index ? { ...row, ...changes } : row)));
  }

  return (
    <div className="space-y-3">
      <input type="hidden" name="projects_json" value={JSON.stringify(projects)} />
      <div className="divide-y divide-white/5 rounded-lg border border-white/10">
        {projects.map((row, index) => {
          const meta = original[row.project_id];
          return (
            <div key={row.project_id} className="space-y-2 px-4 py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-mono text-xs text-ink3">{row.project_id}</p>
                {meta && (
                  <p className="text-xs text-ink3">
                    {meta.source_type} · {meta.confidentiality}
                  </p>
                )}
              </div>
              <input
                type="text"
                aria-label={`Nombre de ${row.project_id}`}
                value={row.safe_name}
                onChange={(e) => update(index, { safe_name: e.target.value })}
                className={inputClass}
              />
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <label className="space-y-1 text-sm">
                  <span className={captionClass}>Estado de la evidencia</span>
                  <select
                    aria-label={`Estado de la evidencia de ${row.project_id}`}
                    value={row.evidence_status}
                    onChange={(e) =>
                      update(index, {
                        evidence_status: e.target.value as Project["evidence_status"],
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
                    aria-label={`Uso en CV de ${row.project_id}`}
                    value={row.cv_usage}
                    onChange={(e) =>
                      update(index, { cv_usage: e.target.value as ProjectCvUsage })
                    }
                    className={selectClass}
                  >
                    {Object.entries(PROJECT_CV_USAGE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className={captionClass}>Uso en entrevista</span>
                  <select
                    aria-label={`Uso en entrevista de ${row.project_id}`}
                    value={row.interview_usage}
                    onChange={(e) =>
                      update(index, {
                        interview_usage: e.target.value as ProjectCvUsage,
                      })
                    }
                    className={selectClass}
                  >
                    {Object.entries(PROJECT_CV_USAGE_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="block space-y-1 text-sm">
                <span className={captionClass}>Confirmaciones pendientes</span>
                <input
                  type="text"
                  aria-label={`Confirmaciones pendientes de ${row.project_id}`}
                  value={row.pending_confirmations.join(", ")}
                  onChange={(e) =>
                    update(index, {
                      pending_confirmations: e.target.value
                        .split(",")
                        .map((entry) => entry.trim())
                        .filter(Boolean),
                    })
                  }
                  className={inputClass}
                />
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ProjectCatalogForm({ current }: { current: ProjectCatalog }) {
  const [projects, setProjects] = useState<ProjectEdit[]>(() =>
    current.projects.map(toEdit),
  );
  const original = Object.fromEntries(current.projects.map((p) => [p.project_id, p]));
  const [state, action, pending] = useActionState<ProjectCatalogFormState, FormData>(
    reviewProjectCatalog,
    INITIAL_PROJECT_CATALOG_STATE,
  );
  const router = useRouter();

  useEffect(() => {
    if (state.saved) router.refresh();
  }, [state.saved, router]);

  return (
    <form action={action} className="space-y-8">
      <header className="space-y-1">
        <h2 className="text-2xl font-semibold tracking-tight">Catálogo de proyectos</h2>
        <p className="text-sm text-ink2">
          Versión {current.version} · actualizado el {current.updated_at}
        </p>
      </header>

      <section className="space-y-3">
        <h2 className={sectionTitleClass}>Proyectos</h2>
        <ProjectRowEditor
          projects={projects}
          original={original}
          onChange={setProjects}
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
