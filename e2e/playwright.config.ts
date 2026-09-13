import { defineConfig, devices } from "@playwright/test";

/**
 * Corre contra la app ya levantada, no contra un servidor que Playwright
 * arranque: lo que se quiere probar es el stack de Compose completo —Caddy
 * enrutando, `web` renderizando en servidor, `api` y Postgres detrás—, que
 * es exactamente lo que M0 tiene que garantizar.
 *
 * En CI, el workflow hace `docker compose up` antes de invocarlo.
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  // Una CI compartida es más lenta por operación que un portátil, y el
  // primer `git clone` real del clon de escritura de /perfil -que no
  // existe hasta la primera petición, y en CI arranca siempre en frío- por
  // sí solo puede acercarse a los 5s por defecto de `expect`. Se ensancha
  // solo en CI: en local ese clon ya está caliente de sesiones anteriores,
  // y fallar rápido ahí es más útil al iterar (docs/decisions/
  // fase-2-perfil-editable.md, 2026-09-13).
  expect: process.env.CI ? { timeout: 15_000 } : undefined,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
