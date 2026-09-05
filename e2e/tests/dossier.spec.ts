import { expect, test } from "@playwright/test";

/**
 * El recorrido de M3 de punta a punta: con una oferta ya puntuada, confirmar
 * una variante de CV y descargar su PDF.
 *
 * Asume `LLM_PROVIDER=stub` y el repositorio de datos **sintético** que
 * monta `docker-compose.override.yml` por omisión, con un PDF de mentira en
 * cada carpeta de variante -ver `services/api/tests/fixtures/data_repo/` y
 * su cabecera-. Ni la extracción ni la puntuación llaman a nada real, así
 * que el recorrido es determinista y gratis.
 */

function anuncioInventado(): string {
  const marca = `ref-${Date.now()}`;
  return [
    `Astillero Nube — Ingeniero de Datos (${marca})`,
    "",
    "Buscamos una persona para los pipelines de ingesta de datos de sensores",
    "de las cooperativas agrícolas con las que trabajamos en Sevilla.",
    "",
    "Qué pedimos",
    "- Imprescindible SQL avanzado.",
    "- Al menos tres años en ingeniería de datos.",
    "- Se valora Python y orquestadores de flujos.",
    "",
    "Condiciones",
    "- Banda de 38.000 a 46.000 euros brutos anuales.",
    "- Modalidad híbrida, dos días en oficina.",
  ].join("\n");
}

async function pegarYEsperar(page: import("@playwright/test").Page) {
  await page.goto("/capturar");
  await page.getByLabel("Texto del anuncio").fill(anuncioInventado());
  await page.getByRole("button", { name: "Capturar y extraer" }).click();
  await expect(page).toHaveURL(/\/ofertas\/[0-9a-f-]{36}$/);
  await expect(
    page.getByRole("heading", { name: "Procedencia de la puntuación" }),
  ).toBeVisible({ timeout: 60_000 });
}

test("confirmar una variante la marca como confirmada y no borra la anterior", async ({
  page,
}) => {
  await pegarYEsperar(page);

  await expect(
    page.getByRole("heading", { name: "Confirmar o cambiar" }),
  ).toBeVisible();
  await expect(
    page.getByText("Todavía no se ha confirmado ninguna variante."),
  ).toBeVisible();

  // La primera fila de variantes disponibles, sea o no la recomendada: el
  // punto de este test es el mecanismo de confirmar, no cuál se recomienda.
  await page.getByRole("button", { name: "Confirmar" }).first().click();

  await expect(page.getByText(/✓ confirmada: /)).toBeVisible();
  await expect(
    page.getByText("Todavía no se ha confirmado ninguna variante."),
  ).toHaveCount(0);
});

test("el PDF de una variante se descarga con el tipo correcto", async ({
  page,
}) => {
  await pegarYEsperar(page);

  const enlace = page.getByRole("link", { name: "Ver PDF" }).first();
  const href = await enlace.getAttribute("href");
  expect(href).toMatch(/\/api\/offers\/[0-9a-f-]{36}\/cv\?variant=/);

  // La cookie de sesión del navegador viaja con `page.request`, así que esto
  // comprueba lo mismo que vería quien hace clic: el mismo origen que sirve
  // la pantalla también sirve el PDF, sin CORS de por medio.
  const respuesta = await page.request.get(href!);
  expect(respuesta.status()).toBe(200);
  expect(respuesta.headers()["content-type"]).toBe("application/pdf");
  const cuerpo = await respuesta.body();
  expect(cuerpo.subarray(0, 5).toString("latin1")).toBe("%PDF-");
});
