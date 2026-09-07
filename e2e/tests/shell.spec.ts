import { expect, test } from "@playwright/test";

/**
 * La estructura del shell mínimo, decidida el 2026-09-06 al empezar Fase 2:
 * barra lateral en escritorio y barra inferior en móvil, con las tres
 * entradas que hoy tienen pantalla real (Pipeline, Capturar, Perfil) — no
 * las siete de `docs/APP_SCREENS.md` del repositorio privado, que incluye
 * Hoy, Oferta, CVs y Stats sin ruta construida todavía.
 *
 * Igual que `dossier.spec.ts`: aserciones de qué existe y en qué orden, no
 * comparación visual de píxeles.
 */

// El icono va en un `<span aria-hidden>` -invisible para lectores de
// pantalla- pero Playwright lee el texto del DOM tal cual, iconos
// incluidos, así que el texto esperado los lleva también.
const ENTRADAS = ["▤Pipeline", "＋Capturar", "◇Perfil"];

test("la barra lateral de escritorio trae las tres entradas en orden", async ({
  page,
}) => {
  await page.goto("/capturar");
  const nav = page.getByRole("navigation", { name: "Principal", exact: true });
  await expect(nav).toBeVisible();
  await expect(nav.getByRole("link")).toHaveText(ENTRADAS);
  await expect(nav.getByRole("link", { name: "Capturar" })).toHaveAttribute(
    "aria-current",
    "page",
  );

  // La barra inferior de móvil existe en el DOM pero `md:hidden` la esconde.
  await expect(
    page.getByRole("navigation", { name: "Principal (móvil)" }),
  ).toBeHidden();
});

test("la barra inferior de móvil trae las mismas tres entradas", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/capturar");
  const nav = page.getByRole("navigation", { name: "Principal (móvil)" });
  await expect(nav).toBeVisible();
  await expect(nav.getByRole("link")).toHaveText(ENTRADAS);

  await expect(
    page.getByRole("navigation", { name: "Principal", exact: true }),
  ).toBeHidden();
});

test("Perfil es un destino real, dentro del shell", async ({ page }) => {
  await page.goto("/perfil");
  // El contenido real -el editor de objectives.yaml, M0 de Fase 2- llega
  // en el mismo commit que este test; lo que importa aquí es que "Perfil"
  // ya no es un marcador y vive dentro del shell, no cómo es la pantalla.
  await expect(page.getByRole("heading", { name: "Objetivos" })).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Principal", exact: true }),
  ).toBeVisible();
});
