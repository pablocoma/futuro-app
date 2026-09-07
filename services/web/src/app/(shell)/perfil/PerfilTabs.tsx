"use client";

import { useState } from "react";

import type {
  BulletBank,
  Constraints,
  Objectives,
  Preferences,
  RoleVariantContent,
} from "@/lib/api";

import { BulletBankForm } from "./BulletBankForm";
import { ConstraintsForm } from "./ConstraintsForm";
import { ObjectivesForm } from "./ObjectivesForm";
import { PreferencesForm } from "./PreferencesForm";
import { RoleVariantsForm } from "./RoleVariantsForm";

type Tab = "objetivos" | "preferencias" | "restricciones" | "bullets" | "variantes";

const TABS: { id: Tab; label: string }[] = [
  { id: "objetivos", label: "Objetivos" },
  { id: "preferencias", label: "Preferencias" },
  { id: "restricciones", label: "Restricciones" },
  { id: "bullets", label: "Bullets" },
  { id: "variantes", label: "Variantes de rol" },
];

/**
 * Las cinco vistas de `/perfil`, alternadas con un selector arriba sin
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
}: {
  objectives: Objectives;
  preferences: Preferences;
  constraints: Constraints;
  bulletBank: BulletBank;
  roleVariants: RoleVariantContent;
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
    </div>
  );
}
