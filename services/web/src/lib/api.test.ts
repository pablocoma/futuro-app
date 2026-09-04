import { beforeEach, describe, expect, it, vi } from "vitest";

const cookieHeader = vi.hoisted(() => ({ value: "" }));

vi.mock("next/headers", () => ({
  cookies: async () => ({ toString: () => cookieHeader.value }),
}));

const { getCurrentUser, getHealth, ingestOffer, listOffers } = await import(
  "@/lib/api",
);

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

describe("escrituras", () => {
  beforeEach(() => {
    cookieHeader.value = "";
    vi.unstubAllGlobals();
  });

  it("manda el anuncio como JSON con las cookies de la sesión", async () => {
    cookieHeader.value = "futuro_session=abc";
    const fetchMock = mockFetch(202, { capture_id: "una-oferta" });

    const result = await ingestOffer({ raw_text: "un anuncio inventado" });

    expect(result).toEqual({ ok: true, data: { capture_id: "una-oferta" } });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api:8000/api/offers/ingest",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ raw_text: "un anuncio inventado" }),
        headers: {
          cookie: "futuro_session=abc",
          "content-type": "application/json",
        },
      }),
    );
  });

  it("devuelve el motivo de un error, no solo que falló", async () => {
    // Quien acaba de pegar un anuncio tiene derecho a saber por qué no se
    // ha guardado, así que una escritura fallida no puede devolver null y
    // ya está, como hacen las lecturas.
    mockFetch(503, { detail: "la cola de trabajos no está disponible" });

    await expect(ingestOffer({ raw_text: "x" })).resolves.toEqual({
      ok: false,
      status: 503,
      detail: "la cola de trabajos no está disponible",
    });
  });

  it("saca un mensaje legible de un error de validación de FastAPI", async () => {
    // Los 422 no traen `detail` como cadena sino como lista de problemas.
    mockFetch(422, {
      detail: [{ loc: ["body", "raw_text"], msg: "String should have at least 200 characters" }],
    });

    const result = await ingestOffer({ raw_text: "corto" });

    expect(result).toMatchObject({
      ok: false,
      detail: "String should have at least 200 characters",
    });
  });

  it("dice que no hay API cuando la petición ni sale", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("ECONNREFUSED");
      }),
    );

    await expect(ingestOffer({ raw_text: "x" })).resolves.toMatchObject({
      ok: false,
      status: 0,
    });
  });

  it("lista las ofertas capturadas", async () => {
    mockFetch(200, [{ id: "una", title: "Ingeniero de Datos" }]);
    await expect(listOffers()).resolves.toHaveLength(1);
  });
});
