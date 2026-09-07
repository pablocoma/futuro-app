import { expect, test } from "@playwright/test";

/**
 * El recorrido de M0 de Fase 2 de punta a punta: editar
 * `config/objectives.yaml`, ver el diff sin escribir nada, y confirmar
 * -que escribe, commitea y empuja de verdad-.
 *
 * Contra el remoto de git local que siembra `make seed-data-repo-write`
 * (enganchado a `make up`), no contra GitHub ni el repositorio privado
 * real. El estado se acumula entre ejecuciones -igual que las ofertas en
 * Postgres en el resto de la suite-, así que la declaración lleva una
 * marca única para no depender de lo que dejó una ejecución anterior.
 */

test("editar el objetivo, ver el diff sin escribir, y confirmar lo escribe y empuja", async ({
  page,
}) => {
  const marca = `e2e-${Date.now()}`;
  const declaracion = `Declaración de prueba ${marca}.`;

  await page.goto("/perfil");
  await expect(page.getByRole("heading", { name: "Objetivos" })).toBeVisible();

  await page.getByLabel("Declaración").fill(declaracion);
  await page.getByRole("button", { name: "Ver cambios" }).click();

  const diff = page.locator("pre");
  await expect(diff).toBeVisible();
  await expect(diff).toContainText(declaracion);
  await expect(
    page.getByRole("heading", { name: "Diff, sin escribir todavía" }),
  ).toBeVisible();

  // Todavía no se ha escrito nada: el botón de confirmar ya está
  // habilitado, pero no se ha pulsado.
  const confirmar = page.getByRole("button", { name: "Confirmar y guardar" });
  await expect(confirmar).toBeEnabled();

  await confirmar.click();
  await expect(
    page.getByRole("heading", { name: "Escrito y empujado" }),
  ).toBeVisible();
  await expect(page.getByText(/commit [0-9a-f]{12}/)).toBeVisible();

  // Y de verdad quedó escrito: recargar trae la declaración nueva.
  await page.reload();
  await expect(page.getByLabel("Declaración")).toHaveValue(declaracion);
});
