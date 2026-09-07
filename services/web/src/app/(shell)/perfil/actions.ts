"use server";

import {
  commitObjectives,
  diffObjectives,
  type EditableObjectives,
} from "@/lib/api";
import { DECLARABLE_ROLE_FAMILIES } from "@/lib/labels";

// Solo el tipo, no un valor: un fichero "use server" únicamente puede
// exportar funciones async. `INITIAL_OBJECTIVES_STATE` vive en
// `ObjectivesForm.tsx`, que es quien lo necesita.
export type ObjectivesFormState = {
  error: string | null;
  diff: string | null;
  saved: boolean;
  commitSha: string | null;
};

/**
 * Una familia por `<fieldset>`, con tres radios -ninguna / core /
 * exploratoria-: es lo que hace imposible que el formulario mande una
 * familia repetida entre las dos listas, en vez de dejar que el 422 de la
 * API lo diga después de escribir texto libre.
 */
function parseEdit(formData: FormData): EditableObjectives {
  const core: string[] = [];
  const exploratory: string[] = [];
  for (const family of DECLARABLE_ROLE_FAMILIES) {
    const choice = formData.get(`family_${family}`);
    if (choice === "core") core.push(family);
    if (choice === "exploratory") exploratory.push(family);
  }

  const successDimensions = String(formData.get("success_dimensions") ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);

  return {
    transition: {
      target_year: Number(formData.get("target_year")),
      urgency: String(formData.get("urgency") ?? "").trim(),
      expected_tenure_years: [
        Number(formData.get("tenure_min")),
        Number(formData.get("tenure_max")),
      ],
    },
    primary_objective: {
      statement: String(formData.get("statement") ?? "").trim(),
    },
    success_dimensions: successDimensions,
    role_families: { core, exploratory },
  };
}

/**
 * Un único action para las dos mitades del mecanismo: qué botón se ha
 * pulsado decide si se calcula el diff o si se commitea y empuja, pero los
 * dos parten del mismo formulario y del mismo `parseEdit`.
 */
export async function reviewObjectives(
  _previous: ObjectivesFormState,
  formData: FormData,
): Promise<ObjectivesFormState> {
  const intent = String(formData.get("intent") ?? "diff");
  const edit = parseEdit(formData);

  if (intent === "commit") {
    const result = await commitObjectives(edit);
    if (!result.ok) {
      return { error: result.detail, diff: null, saved: false, commitSha: null };
    }
    return {
      error: null,
      diff: result.data.diff,
      saved: true,
      commitSha: result.data.commit_sha,
    };
  }

  const result = await diffObjectives(edit);
  if (!result.ok) {
    return { error: result.detail, diff: null, saved: false, commitSha: null };
  }
  return { error: null, diff: result.data.diff, saved: false, commitSha: null };
}
