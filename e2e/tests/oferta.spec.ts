import { expect, test } from "@playwright/test";

/**
 * El recorrido de M1 de punta a punta: pegar un anuncio, esperar a que el
 * worker lo extraiga, y ver lo extraído con la evidencia de cada campo.
 *
 * Es lo único que comprueba la cadena entera —Caddy, Next renderizando en
 * servidor, la API, Redis, arq, el worker y Postgres— trabajando juntos.
 * Ningún test unitario puede ver eso.
 *
 * Asume `LLM_PROVIDER=stub`, que es lo que trae `.env.example`: la
 * extracción se simula a partir del propio texto pegado, así que el
 * resultado es determinista y no cuesta dinero. Y no es un atajo que se
 * salte la validación: las citas de la simulación salen del anuncio y pasan
 * por la misma verificación que las de un modelo de verdad.
 */

// Inventado, y distinto en cada ejecución: el sha256 del texto es único, y
// dos ejecuciones con el mismo anuncio devolverían la captura de la
// primera en vez de encolar nada.
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

test("pegar una oferta, extraerla y ver de dónde sale cada dato", async ({
  page,
}) => {
  const anuncio = anuncioInventado();

  await page.goto("/capturar");
  await page.getByLabel("Texto del anuncio").fill(anuncio);
  await page.getByRole("button", { name: "Capturar y extraer" }).click();

  // La captura lleva a su pantalla, que se refresca sola mientras el worker
  // trabaja. No se sondea nada a mano: si la página no se actualizara, esta
  // espera se agotaría.
  await expect(page).toHaveURL(/\/ofertas\/[0-9a-f-]{36}$/);
  // Se espera a que aparezca la sección de procedencia, que solo se pinta
  // cuando hay extracción: es la señal de que el worker terminó, y no
  // depende de cómo esté redactado el estado.
  await expect(
    page.getByRole("heading", { name: "Procedencia" }),
  ).toBeVisible({ timeout: 30_000 });

  // El título sale del anuncio, con su cita literal debajo.
  await expect(
    page.getByRole("heading", { name: /Cooperativa del Valle/ }),
  ).toBeVisible();
  await expect(page.getByText("● publicado").first()).toBeVisible();

  // Y lo que el anuncio no dice se enseña como ausente, no se rellena: es
  // la regla que gobierna la rebanada entera. La compensación es el caso
  // habitual —en Europa casi ninguna oferta la publica— y aquí tampoco.
  await expect(page.getByText("Mínimo")).toBeVisible();
  await expect(page.getByText("sin datos").first()).toBeVisible();

  // Los requisitos vienen con la cita del fragmento del que salen.
  await expect(page.getByText("Imprescindible SQL y hojas de cálculo.").first()).toBeVisible();

  // Y la procedencia: qué prompt, qué modelo y cuánto costó.
  await expect(page.getByText("offer-extraction/")).toBeVisible();
  await expect(page.getByText("stub", { exact: true })).toBeVisible();
});

test("la oferta capturada aparece en el listado", async ({ page }) => {
  const anuncio = anuncioInventado();

  await page.goto("/capturar");
  await page.getByLabel("Texto del anuncio").fill(anuncio);
  await page.getByRole("button", { name: "Capturar y extraer" }).click();
  await expect(page).toHaveURL(/\/ofertas\/[0-9a-f-]{36}$/);

  await page.goto("/ofertas");
  await expect(page.getByText(/Cooperativa del Valle/).first()).toBeVisible();
});

test("un texto demasiado corto no se acepta y lo dice", async ({ page }) => {
  await page.goto("/capturar");
  await page.getByLabel("Texto del anuncio").fill("Buscamos ingeniero.");
  await page.getByRole("button", { name: "Capturar y extraer" }).click();

  // El error llega a la pantalla en vez de morir en un log, y en
  // castellano: el 422 de la API viene en inglés.
  await expect(page.locator('p[role="alert"]')).toContainText(
    "al menos 200",
  );
  await expect(page).toHaveURL(/\/capturar$/);
});
