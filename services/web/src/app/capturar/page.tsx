import Link from "next/link";

import { CaptureForm } from "./CaptureForm";

export const dynamic = "force-dynamic";

/**
 * Pegar y procesar, en su versión mínima.
 *
 * `docs/APP_SCREENS.md` describe esta pantalla con los pasos de extracción
 * en vivo, para que la espera se vea. Eso llega cuando haya más de un paso
 * que enseñar; de momento la espera se ve en la pantalla de la oferta, que
 * se refresca sola mientras el worker trabaja.
 */
export default function Page() {
  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-12">
      <header className="space-y-2">
        <p className="font-mono text-xs uppercase tracking-widest text-ink3">
          Capturar
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">
          Pegar una oferta
        </h1>
        <p className="text-sm text-ink2">
          El texto se guarda tal cual y se extrae en segundo plano. Los demás
          canales —URL, extensión, Telegram, correo— llegan más adelante.
        </p>
      </header>

      <CaptureForm />

      <Link href="/ofertas" className="inline-block text-sm text-ink2 hover:text-acc">
        ← Ofertas capturadas
      </Link>
    </main>
  );
}
