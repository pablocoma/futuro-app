import {
  getBulletBank,
  getConstraints,
  getCvVariants,
  getObjectives,
  getPreferences,
  getProjectCatalog,
  getRoleVariants,
  getScoringModel,
} from "@/lib/api";

import { PerfilTabs } from "./PerfilTabs";

export const dynamic = "force-dynamic";

/**
 * Fase 2, M0 (`objectives.yaml`), M1 (`preferences.yaml`,
 * `constraints.yaml`), M2 (`professional_bullet_bank.yaml`,
 * `role_variant_content.yaml`), M3 (`cv_variants.yaml`,
 * `project_catalog.yaml`) y M4 (`scoring_model.yaml`, la última rebanada
 * de Fase 2): ocho ficheros, ocho formularios, una sola pantalla con
 * pestañas -`PerfilTabs`-. Los ocho `get*` ya hacen `pull --rebase` antes
 * de devolver nada -ver `data_repo_write/router.py`-, así que cada
 * formulario arranca sobre lo último que hay en el remoto, no sobre una
 * copia local vieja.
 *
 * Los ocho cuelgan del mismo clon de lectura-escritura, así que si uno
 * falla -sin configurar, repositorio inalcanzable- los otros también: se
 * enseña un único aviso en vez de ocho.
 */
export default async function Page() {
  const [
    objectives,
    preferences,
    constraints,
    bulletBank,
    roleVariants,
    cvVariants,
    projectCatalog,
    scoringModel,
  ] = await Promise.all([
    getObjectives(),
    getPreferences(),
    getConstraints(),
    getBulletBank(),
    getRoleVariants(),
    getCvVariants(),
    getProjectCatalog(),
    getScoringModel(),
  ]);

  const ready =
    objectives !== null &&
    preferences !== null &&
    constraints !== null &&
    bulletBank !== null &&
    roleVariants !== null &&
    cvVariants !== null &&
    projectCatalog !== null &&
    scoringModel !== null;

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
          bulletBank={bulletBank}
          roleVariants={roleVariants}
          cvVariants={cvVariants}
          projectCatalog={projectCatalog}
          scoringModel={scoringModel}
        />
      )}
    </main>
  );
}
