import { getCurrentUser, getHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Página de M0. No es decorativa: es la comprobación de que las cuatro
 * piezas del esqueleto están vivas y hablan entre ellas —Caddy sirviendo,
 * `web` renderizando en servidor, `api` respondiendo y Postgres
 * alcanzable— y de que la sesión que ve el navegador es la que ve el
 * backend.
 *
 * Las siete pantallas reales de `docs/APP_SCREENS.md` empiezan en M1.
 */
export default async function Page() {
  const [health, user] = await Promise.all([getHealth(), getCurrentUser()]);

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-8 px-6 py-16">
      <header className="space-y-2">
        <p className="font-mono text-xs uppercase tracking-widest text-ink3">
          Fase 1 · M0 · esqueleto
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">futuro-app</h1>
        <p className="text-sm text-ink2">
          De una oferta de trabajo a una candidatura lista para enviar.
        </p>
      </header>

      <section className="rounded-lg border border-white/10 bg-white/[0.02]">
        <h2 className="border-b border-white/10 px-5 py-3 font-mono text-xs uppercase tracking-widest text-ink3">
          Servicios
        </h2>
        <dl className="divide-y divide-white/5">
          <Row label="api">
            {health ? (
              <Signal ok={health.status === "ok"}>{health.status}</Signal>
            ) : (
              <Signal ok={false}>sin respuesta</Signal>
            )}
          </Row>
          <Row label="postgres">
            {health ? (
              <Signal ok={health.database === "ok"}>{health.database}</Signal>
            ) : (
              <span className="text-ink3">—</span>
            )}
          </Row>
          <Row label="entorno">
            <span className="font-mono text-ink2">{health?.env ?? "—"}</span>
          </Row>
          <Row label="versión api">
            <span className="font-mono text-ink2">{health?.version ?? "—"}</span>
          </Row>
        </dl>
      </section>

      <section className="rounded-lg border border-white/10 bg-white/[0.02]">
        <h2 className="border-b border-white/10 px-5 py-3 font-mono text-xs uppercase tracking-widest text-ink3">
          Sesión
        </h2>
        <div className="px-5 py-4">
          {user ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1">
                <p className="font-mono text-sm">{user.email}</p>
                <p className="text-xs text-ink3">autenticado vía {user.via}</p>
              </div>
              <form action="/api/auth/logout" method="post">
                <button
                  type="submit"
                  className="rounded-md border border-white/15 px-3 py-1.5 text-sm text-ink2 transition-colors hover:border-acc hover:text-acc"
                >
                  Cerrar sesión
                </button>
              </form>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-ink2">Sin sesión.</p>
              <a
                href="/api/auth/login"
                className="rounded-md bg-acc px-3 py-1.5 text-sm font-medium text-bg transition-opacity hover:opacity-90"
              >
                Entrar con Google
              </a>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-5 py-3">
      <dt className="text-sm text-ink2">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function Signal({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span
      className={`font-mono ${ok ? "text-pos" : "text-neg"}`}
      /* Nunca solo por color: el símbolo lleva la misma información. */
    >
      {ok ? "●" : "▲"} {children}
    </span>
  );
}
