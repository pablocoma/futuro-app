import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieHeader = vi.hoisted(() => ({ value: "" }));

vi.mock("next/headers", () => ({
  cookies: async () => ({ toString: () => cookieHeader.value }),
}));

const { getCurrentUser, getHealth } = await import("@/lib/api");

function mockFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("cliente de la API", () => {
  beforeEach(() => {
    cookieHeader.value = "";
    vi.unstubAllGlobals();
  });

  it("reenvía las cookies de la petición entrante", async () => {
    cookieHeader.value = "futuro_session=abc";
    const fetchMock = mockFetch(200, { email: "a@b.test", via: "google" });

    await getCurrentUser();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api:8000/api/auth/me",
      expect.objectContaining({ headers: { cookie: "futuro_session=abc" } }),
    );
  });

  it("no manda cabecera de cookie cuando no hay ninguna", async () => {
    const fetchMock = mockFetch(401, {});

    await getCurrentUser();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api:8000/api/auth/me",
      expect.objectContaining({ headers: {} }),
    );
  });

  it("devuelve null sin sesión, en vez de propagar el 401", async () => {
    mockFetch(401, { detail: "no autenticado" });
    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("conserva el cuerpo de un 503 para poder pintar el estado degradado", async () => {
    // La API responde 503 cuando Postgres no contesta, pero el cuerpo dice
    // *qué* está caído: descartarlo dejaría la página sin poder distinguir
    // "api caída" de "base de datos caída".
    mockFetch(503, {
      status: "degraded",
      env: "development",
      version: "0.1.0",
      database: "unreachable",
    });

    await expect(getHealth()).resolves.toMatchObject({
      status: "degraded",
      database: "unreachable",
    });
  });

  it("devuelve null si la API no responde, sin lanzar", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("ECONNREFUSED");
      }),
    );
    await expect(getHealth()).resolves.toBeNull();
  });
});
