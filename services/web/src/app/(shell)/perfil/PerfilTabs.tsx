"use client";

import { useState } from "react";

import type {
  BulletBank,
  Constraints,
  CvVariants,
  Objectives,
  Preferences,
  ProjectCatalog,
  RoleVariantContent,
  ScoringModel,
} from "@/lib/api";

import { BulletBankForm } from "./BulletBankForm";
import { ConstraintsForm } from "./ConstraintsForm";
import { CvVariantsForm } from "./CvVariantsForm";
import { ObjectivesForm } from "./ObjectivesForm";
import { PreferencesForm } from "./PreferencesForm";
import { ProjectCatalogForm } from "./ProjectCatalogForm";
import { RoleVariantsForm } from "./RoleVariantsForm";
import { ScoringModelForm } from "./ScoringModelForm";

type Tab =
  | "objetivos"
  | "preferencias"
  | "restricciones"
  | "bullets"
  | "variantes"
  | "variantes_cv"
  | "catalogo"
  | "scoring";

const TABS: { id: Tab; label: string }[] = [
  { id: "objetivos", label: "Objetivos" },
  { id: "preferencias", label: "Preferencias" },
  { id: "restricciones", label: "Restricciones" },
  { id: "bullets", label: "Bullets" },
  { id: "variantes", label: "Variantes de rol" },
  { id: "variantes_cv", label: "Variantes de CV" },
  { id: "catalogo", label: "Catálogo de proyectos" },
  { id: "scoring", label: "Modelo de scoring" },
];

/**
 * Las ocho vistas de `/perfil`, alternadas con un selector arriba sin
 * cambiar de URL -mismo patrón que `docs/APP_SCREENS.md` documenta para
 * Pipeline/CVs/Stats-. Cada pestaña es un fichero YAML distinto con su
 * propio ciclo diff/commit independiente; cambiar de pestaña no descarta
 * un diff a medias de otra -cada `<Form>` mantiene su propio estado de
 * React y solo se desmonta, no se comparte entre pestañas-.
 */
export function PerfilTabs({
  objectives,
  preferences,
  constraints,
  bulletBank,
  roleVariants,
  cvVariants,
  projectCatalog,
  scoringModel,
}: {
  objectives: Objectives;
  preferences: Preferences;
  constraints: Constraints;
  bulletBank: BulletBank;
  roleVariants: RoleVariantContent;
  cvVariants: CvVariants;
  projectCatalog: ProjectCatalog;
  scoringModel: ScoringModel;
}) {
  const [tab, setTab] = useState<Tab>("objetivos");

  return (
    <div className="space-y-8">
      <nav className="flex flex-wrap gap-6 border-b border-white/10">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={tab === t.id ? "tab tab-active" : "tab"}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {tab === "objetivos" && <ObjectivesForm current={objectives} />}
      {tab === "preferencias" && <PreferencesForm current={preferences} />}
      {tab === "restricciones" && <ConstraintsForm current={constraints} />}
      {tab === "bullets" && <BulletBankForm current={bulletBank} />}
      {tab === "variantes" && <RoleVariantsForm current={roleVariants} />}
      {tab === "variantes_cv" && <CvVariantsForm current={cvVariants} />}
      {tab === "catalogo" && <ProjectCatalogForm current={projectCatalog} />}
      {tab === "scoring" && <ScoringModelForm current={scoringModel} />}
    </div>
  );
}
