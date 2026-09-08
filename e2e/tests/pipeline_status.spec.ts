import { expect, test } from "@playwright/test";

/**
 * El estado de una candidatura (Fase 3, rebanada 1): un botón por etapa, sin
 * orden forzado. No depende de la extracción ni de la puntuación -es una
 * línea de tiempo aparte-, así que el recorrido no espera al worker: la
 * sección ya está en pantalla en cuanto se captura la oferta.
 */

function anuncioInventado(): string {
  const marca = `ref-${Date.now()}`;
  return [
    `Cooperativa del Valle — Analista de Datos (${marca})`,
    "",
    "Buscamos una persona para el equipo de logística del almacén de Teruel,",
    "trabajando con los cuadros de mando de la cadena de frío.",
    "",
    "Qué pedimos",
    "- Imprescindible SQL y hojas de cálculo.",
    "- Se valora experiencia con herramientas de visualización.",
    "- Carné de conducir B.",
    "",
    "Condiciones",
    "- Jornada completa y contrato indefinido.",
    "- Dos días de teletrabajo a la semana.",
  ].join("\n");
}

test("una oferta recién capturada está en investigación, en la oferta y en el listado", async ({
  page,
}) => {
  await page.goto("/capturar");
  await page.getByLabel("Texto del anuncio").fill(anuncioInventado());
  await page.getByRole("button", { name: "Capturar y extraer" }).click();
  await expect(page).toHaveURL(/\/ofertas\/[0-9a-f-]{36}$/);

  await expect(
    page.getByRole("heading", { name: "Estado de la candidatura" }),
  ).toBeVisible();
  await expect(page.getByText("✓ en investigación")).toBeVisible();

  await page.goto("/ofertas");
  await expect(page.getByText("en investigación").first()).toBeVisible();
});

test("cambiar de etapa se refleja en la oferta y en el listado, sin tocar el dossier", async ({
  page,
}) => {
  await page.goto("/capturar");
  await page.getByLabel("Texto del anuncio").fill(anuncioInventado());
  await page.getByRole("button", { name: "Capturar y extraer" }).click();
  await expect(page).toHaveURL(/\/ofertas\/[0-9a-f-]{36}$/);

  await page.getByRole("button", { name: "preparando candidatura" }).click();
  await expect(page.getByText("✓ preparando candidatura")).toBeVisible();

  await page.goto("/ofertas");
  await expect(page.getByText("preparando candidatura").first()).toBeVisible();
});

test("cualquier etapa a cualquier otra: de investigación directo a cerrada", async ({
  page,
}) => {
  await page.goto("/capturar");
  await page.getByLabel("Texto del anuncio").fill(anuncioInventado());
  await page.getByRole("button", { name: "Capturar y extraer" }).click();
  await expect(page).toHaveURL(/\/ofertas\/[0-9a-f-]{36}$/);

  await page.getByRole("button", { name: "cerrada" }).click();
  await expect(page.getByText("✓ cerrada")).toBeVisible();
});
