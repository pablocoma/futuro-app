import { beforeEach, describe, expect, it, vi } from "vitest";

const currentUser = vi.hoisted(() => ({ value: null as unknown }));
const redirected = vi.hoisted(() => ({ to: null as string | null }));

vi.mock("@/lib/api", () => ({
  getCurrentUser: async () => currentUser.value,
}));

vi.mock("next/navigation", () => ({
  redirect: (path: string) => {
    redirected.to = path;
    // `redirect` de Next funciona lanzando; imitarlo importa porque el
    // código que sigue a `requireUser` no debe ejecutarse sin sesión.
    throw new Error("NEXT_REDIRECT");
  },
}));

const { requireUser } = await import("@/lib/session");

describe("requireUser", () => {
  beforeEach(() => {
    currentUser.value = null;
    redirected.to = null;
  });

  it("devuelve el usuario cuando hay sesión", async () => {
    currentUser.value = { email: "a@b.test", via: "google" };
    await expect(requireUser()).resolves.toEqual({
      email: "a@b.test",
      via: "google",
    });
    expect(redirected.to).toBeNull();
  });

  it("manda a la pantalla de inicio cuando no hay sesión", async () => {
    await expect(requireUser()).rejects.toThrow("NEXT_REDIRECT");
    expect(redirected.to).toBe("/");
  });

  it("acepta la sesión del bypass de desarrollo", async () => {
    // En local `DEV_AUTH_BYPASS` autentica sin cookie. Un guardián que
    // mirase la cookie mandaría a inicio y rompería el desarrollo y el E2E.
    currentUser.value = { email: "dev@localhost", via: "dev-bypass" };
    await expect(requireUser()).resolves.toMatchObject({ via: "dev-bypass" });
    expect(redirected.to).toBeNull();
  });
});
