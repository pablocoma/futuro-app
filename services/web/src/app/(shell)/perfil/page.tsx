import { getConstraints, getObjectives, getPreferences } from "@/lib/api";

import { PerfilTabs } from "./PerfilTabs";

export const dynamic = "force-dynamic";

/**
 * Fase 2, M0 (`objectives.yaml`) y M1 (`preferences.yaml`,
 * `constraints.yaml`): tres ficheros, tres formularios, una sola pantalla
 * con pestañas -`PerfilTabs`-. Los tres `get*` ya hacen `pull --rebase`
 * antes de devolver nada -ver `data_repo_write/router.py`-, así que cada
 * formulario arranca sobre lo último que hay en el remoto, no sobre una
 * copia local vieja.
 *
 * Los tres cuelgan del mismo clon de lectura-escritura, así que si uno
 * falla -sin configurar, repositorio inalcanzable- los otros dos también:
 * se enseña un único aviso en vez de tres.
 */
export default async function Page() {
  const [objectives, preferences, constraints] = await Promise.all([
    getObjectives(),
    getPreferences(),
    getConstraints(),
  ]);

  const ready = objectives !== null && preferences !== null && constraints !== null;

  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-12">
      <header className="space-y-2">
        <p className="font-mono text-xs uppercase tracking-widest text-ink3">
          Perfil
        </p>
      </header>

      {!ready ? (
        <p className="font-mono text-sm text-neg">
          ▲ El mecanismo de escritura del perfil no está disponible: sin
          clon de lectura-escritura configurado, o el repositorio privado no
          responde.
        </p>
      ) : (
        <PerfilTabs
          objectives={objectives}
          preferences={preferences}
          constraints={constraints}
        />
      )}
    </main>
  );
}
