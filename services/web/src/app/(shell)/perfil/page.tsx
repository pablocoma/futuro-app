import { getObjectives } from "@/lib/api";

import { ObjectivesForm } from "./ObjectivesForm";

export const dynamic = "force-dynamic";

/**
 * El primer fichero editable de Fase 2: `config/objectives.yaml`.
 *
 * `getObjectives` ya hace `pull --rebase` antes de devolver nada -ver
 * `data_repo_write/router.py`-, así que el formulario siempre arranca
 * sobre lo último que hay en el remoto, no sobre una copia local vieja.
 */
export default async function Page() {
  const current = await getObjectives();

  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-12">
      <header className="space-y-2">
        <p className="font-mono text-xs uppercase tracking-widest text-ink3">
          Perfil
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">Objetivos</h1>
        {current && (
          <p className="text-sm text-ink2">
            Versión {current.version} · actualizado el {current.updated_at}
          </p>
        )}
      </header>

      {current === null ? (
        <p className="font-mono text-sm text-neg">
          ▲ El mecanismo de escritura del perfil no está disponible: sin
          clon de lectura-escritura configurado, o el repositorio privado no
          responde.
        </p>
      ) : (
        <ObjectivesForm current={current} />
      )}
    </main>
  );
}
