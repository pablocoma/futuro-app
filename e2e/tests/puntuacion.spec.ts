import { expect, test } from "@playwright/test";

/**
 * El recorrido de M2 de punta a punta: pegar un anuncio, esperar a que el
 * worker lo extraiga **y lo puntúe**, y ver la composición ponderada.
 *
 * La puntuación no se pide: la extracción la encadena al terminar bien, y
 * eso es justamente lo que este test comprueba. Si el encadenado se
 * rompiera, aquí no aparecería ninguna nota y la espera se agotaría.
 *
 * Asume `LLM_PROVIDER=stub` y el repositorio de datos **sintético** que
 * monta `docker-compose.override.yml`: cuatro dimensiones inventadas con
 * pesos 40/30/20/10 y cuatro variantes de una persona que no existe. Así el
 * recorrido es determinista, gratis, y no toca el repositorio privado.
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
  // La procedencia de la **puntuación** solo se pinta cuando el segundo
  // trabajo ha terminado, así que esperarla es esperar la cadena entera:
  // extraer, encolar la puntuación, puntuar y elegir variante.
  await expect(
    page.getByRole("heading", { name: "Procedencia de la puntuación" }),
  ).toBeVisible({ timeout: 60_000 });
}

test("una oferta pegada se puntúa sola y enseña su composición", async ({
  page,
}) => {
  await pegarYEsperar(page);

  // El número grande, sin escala al lado.
  await expect(page.getByText(/^cobertura \d+%/)).toBeVisible();

  // La composición ponderada, con su descripción para quien no la ve: es
  // una sola imagen accesible y no un montón de divs sueltos, porque leer
  // «40%, 3, 30%, sin puntuar» celda a celda no dice nada.
  const grafico = page.getByRole("img", { name: /Composición ponderada/ });
  await expect(grafico).toBeVisible();
  await expect(grafico).toHaveAttribute("aria-label", /peso 40, nota \d de 5/);
  // Y lo que no se pudo puntuar se dice, en vez de ocultarse.
  await expect(grafico).toHaveAttribute("aria-label", /sin puntuar/);

  // Cada nota con la cita que la sostiene y el ancla que la explica: la
  // evidencia con el mismo peso que el dato, igual que en la extracción.
  await expect(
    page.getByRole("heading", { name: "Por qué cada nota" }),
  ).toBeVisible();
  await expect(page.getByText(/^ancla: /).first()).toBeVisible();

  // Los nombres de dimensión salen del repositorio de datos y se pintan
  // humanizados, sin traducir: el vocabulario es del repositorio privado y
  // aquí no se duplica.
  // Aparece dos veces a propósito: como etiqueta debajo de su barra y como
  // fila del detalle. Se comprueba la del detalle, que es la que lleva la
  // nota al lado.
  await expect(
    page.getByText("Ahorro estimado", { exact: true }).last(),
  ).toBeVisible();
});

test("los filtros distinguen «sin comprobar» de «no cumple»", async ({
  page,
}) => {
  await pegarYEsperar(page);

  await expect(
    page.getByRole("heading", { name: "Filtros eliminatorios" }),
  ).toBeVisible();
  // El caso habitual: el vehículo contractual casi nunca se publica, así
  // que el filtro queda pendiente. Pendiente no es incumplido, y la
  // pantalla no puede sugerir que lo sea.
  await expect(page.getByText("○ sin comprobar").first()).toBeVisible();
  await expect(page.getByText("▲ no cumple")).toHaveCount(0);
});

test("la variante recomendada se enseña con su motivo", async ({ page }) => {
  await pegarYEsperar(page);

  await expect(
    page.getByRole("heading", { name: "Variante de CV recomendada" }),
  ).toBeVisible();
  // El modelo elige entre documentos que ya existen; el motivo es lo que se
  // le enseña a quien decide.
  await expect(page.getByText(/elección simulada/)).toBeVisible();
  await expect(page.getByText("cv-variant/")).toBeVisible();
});

test("volver a puntuar deja las dos puntuaciones guardadas", async ({
  page,
}) => {
  await pegarYEsperar(page);
  await expect(page.getByText("puntuaciones guardadas")).toBeVisible();

  await page
    .getByRole("button", { name: "Volver a puntuar" })
    .first()
    .click();

  // Append-only: la capa es inmutable y repuntuar inserta. Es lo que hace
  // visible que dos ofertas puntuadas con modelos de scoring distintos no
  // son comparables.
  await expect(page.getByText("2", { exact: true }).first()).toBeVisible({
    timeout: 60_000,
  });
});
