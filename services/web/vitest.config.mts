import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Entorno node: lo que se prueba aquí es el cliente de la API, que
    // corre en el servidor de Next. Las pruebas de componentes llegan
    // cuando haya pantallas con interacción, en M1.
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
