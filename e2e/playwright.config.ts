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
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
