import Link from "next/link";
import { notFound } from "next/navigation";

import { EvidenceDetail, EvidenceMark } from "@/components/Evidence";
import { Refresher } from "@/components/Refresher";
import type { Field, Offer } from "@/lib/api";
import { getOffer } from "@/lib/api";
import { REQUIREMENT_KINDS, STATUS_LABELS, displayValue, labelFor } from "@/lib/labels";

export const dynamic = "force-dynamic";

/**
 * La pantalla de una oferta, en su versión de M1.
 *
 * Enseña lo extraído y, con el mismo peso, de dónde sale cada cosa: la cita
 * del anuncio cuando el dato consta, el razonamiento y la confianza cuando
 * se dedujo, y «sin datos» cuando no aparece. Esa distinción es el proyecto
 * entero, así que no está escondida en un detalle desplegable.
 *
 * La composición ponderada que describe `docs/APP_SCREENS.md` —el ancho de
 * cada barra es el peso de la dimensión, el alto es la nota— necesita el
 * modelo de scoring, que es M2.
 */
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const offer = await getOffer(id);
  if (offer === null) {
    notFound();
  }

  const working =
    offer.extraction_status === "queued" || offer.extraction_status === "running";

  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-12">
      {working ? <Refresher /> : null}

      <header className="space-y-3">
        <Link href="/ofertas" className="text-sm text-ink2 hover:text-acc">
          ← Ofertas
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">
          {titleOf(offer) ?? <span className="text-ink3">Sin título</span>}
        </h1>
        <p className="font-mono text-xs text-ink2">
          {STATUS_LABELS[offer.extraction_status] ?? offer.extraction_status}
          {" · "}
          capturada el{" "}
          {new Date(offer.capture.captured_at).toLocaleString("es-ES")}
        </p>
        {offer.capture.capture_note ? (
          <p className="text-sm text-ink2">Nota: {offer.capture.capture_note}</p>
        ) : null}
      </header>

      {working ? (
        <p className="rounded-lg border border-acc/30 bg-acc/5 px-5 py-3 font-mono text-sm text-acc">
          ◐ Extrayendo. Esta página se actualiza sola.
        </p>
      ) : null}

      {offer.extraction_status === "failed" ? (
        <section className="rounded-lg border border-neg/30 bg-neg/5 px-5 py-4">
          <h2 className="font-mono text-xs uppercase tracking-widest text-neg">
            ▲ La extracción falló
          </h2>
          <p className="mt-2 break-words text-sm text-ink2">
            {offer.extraction_error ?? "sin detalle"}
          </p>
        </section>
      ) : null}

      {offer.extraction ? (
        <>
          <Section title="Empresas">
            <FieldRow
              field={{
                name: "posting_company_id",
                value: offer.extraction.posting_company.name,
                evidence: offer.extraction.posting_company.evidence,
              }}
            />
            <FieldRow
              field={{
                name: "employer_company_id",
                value: offer.extraction.employer_company.name,
                evidence: offer.extraction.employer_company.evidence,
              }}
              suffix={
                offer.extraction.employer_company.confidence
                  ? `confianza ${offer.extraction.employer_company.confidence}`
                  : undefined
              }
            />
          </Section>

          <Section title="Identificación">
            {offer.extraction.identification.map((field) => (
              <FieldRow key={field.name} field={field} />
            ))}
          </Section>

          <Section title="Compensación">
            {offer.extraction.compensation.map((field) => (
              <FieldRow key={field.name} field={field} />
            ))}
          </Section>

          <Section title="Responsabilidades">
            <FieldRow field={offer.extraction.responsibilities} />
          </Section>

          <Section title={`Requisitos (${offer.extraction.requirements.length})`}>
            {offer.extraction.requirements.length === 0 ? (
              <Empty>Ninguno se ha podido sostener con una cita.</Empty>
            ) : (
              offer.extraction.requirements.map((requirement) => (
                <div key={requirement.position} className="space-y-1 px-5 py-3">
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="text-sm">{requirement.text}</span>
                    <span
                      className={`shrink-0 font-mono text-xs ${
                        requirement.kind === "anomalous" ? "text-neg" : "text-ink3"
                      }`}
                    >
                      {requirement.kind === "anomalous" ? "▲ " : ""}
                      {REQUIREMENT_KINDS[requirement.kind] ?? requirement.kind}
                    </span>
                  </div>
                  <blockquote className="border-l-2 border-white/10 pl-2 font-mono text-xs text-ink3">
                    «{requirement.source_quote}»
                  </blockquote>
                  {/* En M1 nunca hay cruce: exige leer el repositorio
                      privado, que es M3. Se dice, en vez de callarlo. */}
                  <p className="text-xs text-ink3">
                    {requirement.match === null
                      ? "sin cruzar con tus evidencias todavía"
                      : requirement.match}
                  </p>
                </div>
              ))
            )}
          </Section>

          {offer.extraction.anomalies.length > 0 ? (
            <Section title="Anomalías">
              {offer.extraction.anomalies.map((anomaly) => (
                <div key={anomaly.position} className="space-y-1 px-5 py-3">
                  <p className="text-sm text-neg">▲ {anomaly.text}</p>
                  <p className="text-sm text-ink2">{anomaly.explanation}</p>
                  <blockquote className="border-l-2 border-white/10 pl-2 font-mono text-xs text-ink3">
                    «{anomaly.source_quote}»
                  </blockquote>
                </div>
              ))}
            </Section>
          ) : null}

          {offer.extraction.corrections.length > 0 ? (
            <Section title="Lo que el código corrigió al modelo">
              {offer.extraction.corrections.map((correction, index) => (
                <div key={index} className="space-y-1 px-5 py-3">
                  <p className="font-mono text-xs text-acc">
                    {labelFor(correction.field)} · {correction.rule}
                  </p>
                  <p className="text-sm text-ink2">{correction.detail}</p>
                  {correction.previous ? (
                    <p className="font-mono text-xs text-ink3">
                      decía «{correction.previous}»
                      {correction.applied ? ` → se guardó «${correction.applied}»` : " → se descartó"}
                    </p>
                  ) : null}
                </div>
              ))}
            </Section>
          ) : null}

          <Section title="Procedencia">
            <Meta label="prompt" value={offer.extraction.prompt_version} />
            <Meta label="modelo" value={offer.extraction.model} />
            <Meta
              label="coste"
              value={
                offer.extraction.cost_usd === null
                  ? "no consta"
                  : `${offer.extraction.cost_usd} USD`
              }
            />
            <Meta
              label="fecha de extracción"
              value={new Date(offer.extraction.extracted_at).toLocaleString("es-ES")}
            />
            <Meta label="versiones" value={String(offer.versions.length)} />
          </Section>
        </>
      ) : null}

      <details className="rounded-lg border border-white/10">
        <summary className="cursor-pointer px-5 py-3 font-mono text-xs uppercase tracking-widest text-ink3">
          Anuncio original
        </summary>
        <pre className="overflow-x-auto whitespace-pre-wrap px-5 pb-5 font-mono text-xs text-ink2">
          {offer.capture.raw_text}
        </pre>
      </details>
    </main>
  );
}

function titleOf(offer: Offer): string | null {
  const title = offer.extraction?.identification.find(
    (field) => field.name === "title",
  );
  return displayValue(title?.value ?? null);
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/[0.02]">
      <h2 className="border-b border-white/10 px-5 py-3 font-mono text-xs uppercase tracking-widest text-ink3">
        {title}
      </h2>
      <div className="divide-y divide-white/5">{children}</div>
    </section>
  );
}

function FieldRow({ field, suffix }: { field: Field; suffix?: string }) {
  const value = displayValue(field.value);
  return (
    <div className="px-5 py-3">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm text-ink2">{labelFor(field.name)}</span>
        <EvidenceMark evidence={field.evidence} />
      </div>
      <p className="mt-0.5 text-sm">
        {value ?? <span className="text-neg">sin datos</span>}
        {value && suffix ? (
          <span className="ml-2 font-mono text-xs text-ink3">{suffix}</span>
        ) : null}
      </p>
      <EvidenceDetail evidence={field.evidence} />
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 px-5 py-2">
      <span className="text-sm text-ink2">{label}</span>
      <span className="font-mono text-xs text-ink2">{value}</span>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-5 py-3 text-sm text-ink3">{children}</p>;
}
