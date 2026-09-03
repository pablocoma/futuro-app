import { expect, test } from "@playwright/test";

/**
 * El smoke test de M0. Comprueba las dos cosas que el esqueleto tiene que
 * garantizar y que ningún test unitario puede ver: que Caddy enruta `/api`
 * a la API y el resto al frontend, y que la página se renderiza en servidor
 * con datos que vienen de la API y de Postgres.
 *
 * Asume DEV_AUTH_BYPASS=true, que es la configuración de .env.example.
 */

test("la API responde sana y con Postgres alcanzable", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({
    status: "ok",
    database: "ok",
  });
});

test("Caddy manda /api a la API y no al frontend", async ({ request }) => {
  // Una ruta inexistente bajo /api tiene que dar el 404 en JSON de FastAPI.
  // Si diera el 404 en HTML de Next, el enrutado estaría al revés, que es
  // el fallo que este esqueleto existe para descartar.
  const response = await request.get("/api/ruta-que-no-existe");
  expect(response.status()).toBe(404);
  expect(response.headers()["content-type"]).toContain("application/json");
});

test("la página pinta el estado del stack y la sesión", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "futuro-app" })).toBeVisible();
  // Renderizado en servidor: el estado viene de la API, no de un fetch del
  // navegador, así que tiene que estar en el HTML inicial.
  await expect(page.getByText("postgres")).toBeVisible();
  await expect(page.getByText("dev@localhost")).toBeVisible();
  await expect(page.getByText("autenticado vía dev-bypass")).toBeVisible();
});
