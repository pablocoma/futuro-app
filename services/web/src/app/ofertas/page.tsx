import Link from "next/link";

import { listOffers } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/labels";
import { requireUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * Listado mínimo, para que una oferta siga siendo alcanzable al recargar.
 *
 * La pantalla Pipeline de `docs/APP_SCREENS.md` —tabla densa, mapa valor ×
 * probabilidad, kanban— necesita el scoring, que es M2. Esto es solo la
 * puerta a la pantalla de una oferta.
 */
export default async function Page() {
  await requireUser();
  const offers = await listOffers();

  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-12">
      <header className="flex items-end justify-between gap-4">
        <div className="space-y-2">
          <p className="font-mono text-xs uppercase tracking-widest text-ink3">
            Ofertas
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Capturadas</h1>
        </div>
        <Link
          href="/capturar"
          className="rounded-md bg-acc px-3 py-1.5 text-sm font-medium text-bg transition-opacity hover:opacity-90"
        >
          Pegar una oferta
        </Link>
      </header>

      {offers === null ? (
        <p className="font-mono text-sm text-neg">▲ La API no responde.</p>
      ) : offers.length === 0 ? (
        <p className="text-sm text-ink2">
          Todavía no hay ninguna. Pega la primera.
        </p>
      ) : (
        <ul className="divide-y divide-white/5 rounded-lg border border-white/10">
          {offers.map((offer) => (
            <li key={offer.id}>
              <Link
                href={`/ofertas/${offer.id}`}
                className="flex items-baseline justify-between gap-4 px-5 py-3 transition-colors hover:bg-white/[0.03]"
              >
                <span className="min-w-0 space-y-0.5">
                  <span className="block truncate text-sm">
                    {offer.title ?? (
                      <span className="text-ink3">sin título todavía</span>
                    )}
                  </span>
                  <span className="block truncate text-xs text-ink3">
                    {offer.company ?? "—"}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-xs text-ink2">
                  {STATUS_LABELS[offer.extraction_status] ??
                    offer.extraction_status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
