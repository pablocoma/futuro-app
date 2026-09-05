import Link from "next/link";
import { notFound } from "next/navigation";

import { Composition } from "@/components/Composition";
import { EvidenceDetail, EvidenceMark } from "@/components/Evidence";
import { Refresher } from "@/components/Refresher";
import type { Assessment, Field, Gate, Offer, RequirementMatch } from "@/lib/api";
import { getOffer } from "@/lib/api";
import {
  ASSESSMENT_STATUS_LABELS,
  EFFORT_LABELS,
  GATE_STATUS_LABELS,
  MATCH_LABELS,
  PORTFOLIO_LABELS,
  PROBABILITY_LABELS,
  REQUIREMENT_KINDS,
  STATUS_LABELS,
  displayValue,
  humanise,
  labelFor,
} from "@/lib/labels";

import { requestAssessment } from "./actions";
import { requireUser } from "@/lib/session";

export const dynamic = "force-dynamic";

/**
 * La pantalla de una oferta, en su versión de M1.
 *
 * Enseña lo extraído y, con el mismo peso, de dónde sale cada cosa: la cita
 * del anuncio cuando el dato consta, el razonamiento y la confianza cuando
 * se dedujo, y «sin datos» cuando no aparece. Esa distinción es el proyecto
 * entero, así que no está escondida en un detalle desplegable.
 *
 * Con M2 gana su composición ponderada: el ancho de cada barra es el peso
 * de la dimensión en el modelo de scoring y el alto es la nota, con un
 * hueco rayado para lo que no se pudo puntuar. Ni un cálculo se hace aquí:
 * los anchos y los altos llegan hechos de la API, y los pesos son los que
 * se guardaron con la fila, no los del modelo de scoring de hoy.
 */
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireUser();
  const { id } = await params;
  const offer = await getOffer(id);
  if (offer === null) {
    notFound();
  }

  // El refresco automático cubre los dos trabajos: tras extraer se encadena
  // la puntuación, así que si solo mirara la extracción la página se
  // quedaría quieta justo cuando aún falta la mitad.
  const busy = (status: string) => status === "queued" || status === "running";
  const working = busy(offer.extraction_status) || busy(offer.assessment_status);

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
          {ASSESSMENT_STATUS_LABELS[offer.assessment_status] ??
            offer.assessment_status}
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
          ◐ {busy(offer.extraction_status) ? "Extrayendo" : "Puntuando"}. Esta
          página se actualiza sola.
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

      {offer.extraction && offer.assessment_status === "failed" ? (
        <section className="rounded-lg border border-neg/30 bg-neg/5 px-5 py-4">
          <h2 className="font-mono text-xs uppercase tracking-widest text-neg">
            ▲ La puntuación falló
          </h2>
          <p className="mt-2 break-words text-sm text-ink2">
            {offer.assessment_error ?? "sin detalle"}
          </p>
          <AssessButton captureId={offer.capture.id} label="Volver a puntuar" />
        </section>
      ) : null}

      {offer.extraction && offer.assessment ? (
        <Scoring
          assessment={offer.assessment}
          variant={offer.variant_recommendation}
          captureId={offer.capture.id}
          versions={offer.assessment_versions.length}
        />
      ) : null}

      {offer.extraction && offer.assessment === null && !working ? (
        <section className="rounded-lg border border-white/10 px-5 py-4">
          <h2 className="font-mono text-xs uppercase tracking-widest text-ink3">
            Sin puntuar
          </h2>
          <p className="mt-2 text-sm text-ink2">
            Esta lectura del anuncio todavía no se ha puntuado. No se estima
            nada mientras tanto: la oferta se queda sin nota, y eso no es lo
            mismo que una nota baja.
          </p>
          <AssessButton captureId={offer.capture.id} label="Puntuar" />
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
                  {/* El cruce contra el banco de evidencias vive en la capa
                      `assessment` y no aquí: `offer_requirements` es
                      inmutable y el cruce tiene que poder recalcularse
                      cuando el banco cambie. Así que `requirement.match` es
                      NULL siempre —«sin evaluar»— y lo que se pinta es la
                      fila del assessment, si la hay. */}
                  <MatchLine
                    match={crossOf(offer.assessment, requirement.position)}
                  />
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
            <Meta label="prompt de extracción" value={offer.extraction.prompt_version} />
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

/**
 * El bloque de puntuación: el número grande, la composición y el detalle.
 *
 * El orden es deliberado. Primero el número, que es lo que se mira; después
 * el dibujo, que dice de dónde sale; y al final el detalle campo a campo,
 * que es donde se puede discutir una nota. Igual que en la extracción, la
 * evidencia va con el mismo peso que el dato: cada nota lleva su cita.
 */
function Scoring({
  assessment,
  variant,
  captureId,
  versions,
}: {
  assessment: Assessment;
  variant: Offer["variant_recommendation"];
  captureId: string;
  versions: number;
}) {
  const coverage = Math.round(Number(assessment.coverage) * 100);

  return (
    <>
      <section className="space-y-6 rounded-lg border border-white/10 px-5 py-5">
        <header className="flex flex-wrap items-end justify-between gap-6">
          <div>
            {/* Número grande y sin escala al lado: la micro-decisión de
                `docs/APP_SCREENS.md`. Un «3.19 / 5» invita a leerlo como un
                porcentaje, y no lo es. */}
            {assessment.value_score === null ? (
              <p className="text-3xl font-semibold tracking-tight text-neg">
                sin puntuación
              </p>
            ) : (
              <p className="text-4xl font-semibold tracking-tight">
                {assessment.value_score}
              </p>
            )}
            <p className="mt-1 font-mono text-xs text-ink3">
              cobertura {coverage}%
              {assessment.source === "recomputed"
                ? " · recalculada sin llamar al modelo"
                : ""}
            </p>
          </div>
          <dl className="flex flex-wrap gap-x-8 gap-y-3">
            <State
              label="probabilidad"
              value={
                PROBABILITY_LABELS[assessment.probability_band] ??
                assessment.probability_band
              }
              tone="acc"
            />
            <State
              label="cartera"
              value={
                assessment.portfolio_bucket === null
                  ? "sin cubo"
                  : (PORTFOLIO_LABELS[assessment.portfolio_bucket] ??
                    assessment.portfolio_bucket)
              }
              tone={assessment.portfolio_bucket === null ? "neg" : "pos"}
            />
            <State
              label="esfuerzo"
              value={
                EFFORT_LABELS[assessment.effort_tier] ?? assessment.effort_tier
              }
              tone={assessment.effort_tier === "skip" ? "neg" : "pos"}
            />
          </dl>
        </header>

        {assessment.value_score === null ? (
          <p className="rounded border border-neg/30 bg-neg/5 px-4 py-3 text-sm text-ink2">
            La cobertura no llega al mínimo que exige el modelo de scoring, así
            que no se emite puntuación. Falta información en las dimensiones
            rayadas de abajo; estimarla contaminaría el histórico.
          </p>
        ) : null}

        {assessment.portfolio_note ? (
          <p className="rounded border border-neg/30 bg-neg/5 px-4 py-3 text-sm text-ink2">
            ▲ {assessment.portfolio_note}
          </p>
        ) : null}

        <Composition assessment={assessment} />

        <div>
          <h3 className="font-mono text-xs uppercase tracking-widest text-ink3">
            Por qué cada nota
          </h3>
          <div className="mt-2 divide-y divide-white/5">
            {assessment.dimensions.map((dimension) => (
              <div key={dimension.dimension} className="space-y-1 py-3">
                <div className="flex items-baseline justify-between gap-4">
                  <span className="text-sm">{humanise(dimension.dimension)}</span>
                  <span
                    className={`shrink-0 font-mono text-xs ${
                      dimension.score === null ? "text-neg" : "text-ink2"
                    }`}
                  >
                    {dimension.score === null
                      ? "— sin puntuar"
                      : `${dimension.score} · peso ${dimension.weight}`}
                  </span>
                </div>
                {dimension.score === null ? (
                  <p className="text-sm text-ink2">
                    {dimension.unscored_reason ?? "sin motivo"}
                  </p>
                ) : (
                  <>
                    {dimension.reason ? (
                      <p className="text-sm text-ink2">{dimension.reason}</p>
                    ) : null}
                    {dimension.citation ? (
                      <blockquote className="border-l-2 border-white/10 pl-2 font-mono text-xs text-ink3">
                        «{dimension.citation}»
                      </blockquote>
                    ) : null}
                    {dimension.anchor ? (
                      <p className="font-mono text-xs text-ink3">
                        ancla: {dimension.anchor}
                      </p>
                    ) : null}
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        <div>
          <h3 className="font-mono text-xs uppercase tracking-widest text-ink3">
            Probabilidad
          </h3>
          <p className="mt-2 text-sm text-ink2">
            {assessment.probability_reason}
          </p>
        </div>
      </section>

      <Section title="Filtros eliminatorios">
        {assessment.gates.map((gate) => (
          <GateRow key={gate.gate} gate={gate} />
        ))}
      </Section>

      <Section title="Variante de CV recomendada">
        {variant === null ? (
          <Empty>No hay recomendación para esta lectura del anuncio.</Empty>
        ) : (
          <div className="space-y-2 px-5 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <span className="font-mono text-sm text-acc">
                {variant.variant}
              </span>
              <span className="font-mono text-xs text-ink3">
                confianza {variant.confidence}
              </span>
            </div>
            <p className="text-sm text-ink2">{variant.reason}</p>
            {/* El PDF se descarga en M3, que es cuando existe el clon del
                repositorio privado desde donde localizarlo. Se dice, en vez
                de dejar un botón que no hace nada. */}
            <p className="font-mono text-xs text-ink3">
              El modelo elige entre los documentos que ya existen; no redacta
              nada. La descarga del PDF llega con M3.
            </p>
            {/* Su propia procedencia, y no la del scoring: la elección de
                variante se hizo con otro prompt y contra otra cosa —la guía
                de `cv/variants/`—, que además cambia cuando cambia la
                estrategia de CV. Meterla en el bloque de la puntuación
                sugeriría que las dos se recalculan juntas, y no: la
                puntuación se recalcula sin el modelo y esto no. */}
            <p className="font-mono text-xs text-ink3">
              {variant.prompt_version} · {variant.model} ·{" "}
              {new Date(variant.recommended_at).toLocaleString("es-ES")}
            </p>
          </div>
        )}
      </Section>

      {assessment.corrections.length > 0 ? (
        <Section title="Lo que el código corrigió al puntuar">
          {assessment.corrections.map((correction, index) => (
            <div key={index} className="space-y-1 px-5 py-3">
              <p className="font-mono text-xs text-acc">
                {correction.field} · {correction.rule}
              </p>
              <p className="text-sm text-ink2">{correction.detail}</p>
              {correction.previous ? (
                <p className="font-mono text-xs text-ink3">
                  decía «{correction.previous}»
                  {correction.applied
                    ? ` → se guardó «${correction.applied}»`
                    : " → se descartó"}
                </p>
              ) : null}
            </div>
          ))}
        </Section>
      ) : null}

      <Section title="Procedencia de la puntuación">
        <Meta
          label="modelo de scoring"
          value={`versión ${assessment.scoring_model_version} · ${assessment.scoring_model_sha256.slice(0, 12)}`}
        />
        <Meta
          label="prompt"
          value={assessment.prompt_version ?? "ninguno (recalculada)"}
        />
        <Meta label="modelo" value={assessment.model ?? "ninguno (recalculada)"} />
        <Meta
          label="coste"
          value={
            assessment.cost_usd === null
              ? "no consta"
              : `${assessment.cost_usd} USD`
          }
        />
        <Meta
          label="fecha"
          value={new Date(assessment.assessed_at).toLocaleString("es-ES")}
        />
        <Meta label="puntuaciones guardadas" value={String(versions)} />
        <div className="px-5 py-3">
          <AssessButton captureId={captureId} label="Volver a puntuar" />
        </div>
      </Section>
    </>
  );
}

/** Un estado: texto con subrayado de color, no una pastilla de fondo. */
function State({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "pos" | "neg" | "acc";
}) {
  const underline = {
    pos: "decoration-pos",
    neg: "decoration-neg",
    acc: "decoration-acc",
  }[tone];
  return (
    <div>
      <dt className="font-mono text-xs uppercase tracking-widest text-ink3">
        {label}
      </dt>
      <dd
        className={`mt-1 text-sm underline decoration-2 underline-offset-4 ${underline}`}
      >
        {value}
      </dd>
    </div>
  );
}

/**
 * Un filtro con su veredicto.
 *
 * `pending` va en el color de alerta y no en rojo de fallo: «no se pudo
 * comprobar» no es «no cumple», y confundirlos es exactamente lo que el
 * modelo de scoring prohíbe. Símbolo además de color, como en todo lo demás.
 */
function GateRow({ gate }: { gate: Gate }) {
  const tone = {
    pass: { color: "text-pos", mark: "●" },
    stretch: { color: "text-acc", mark: "◐" },
    pending: { color: "text-neg", mark: "○" },
    fail: { color: "text-neg", mark: "▲" },
  }[gate.status];

  return (
    <div className="space-y-1 px-5 py-3">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-sm">{humanise(gate.gate)}</span>
        <span className={`shrink-0 font-mono text-xs ${tone.color}`}>
          {tone.mark} {GATE_STATUS_LABELS[gate.status] ?? gate.status}
        </span>
      </div>
      <p className="text-sm text-ink2">{gate.reason}</p>
      {gate.citation ? (
        <blockquote className="border-l-2 border-white/10 pl-2 font-mono text-xs text-ink3">
          «{gate.citation}»
        </blockquote>
      ) : null}
    </div>
  );
}

/** El cruce de un requisito, o que todavía no se ha cruzado. */
function MatchLine({ match }: { match: RequirementMatch | null }) {
  if (match === null) {
    return (
      <p className="text-xs text-ink3">sin cruzar con tus evidencias todavía</p>
    );
  }
  return (
    <p className="text-xs text-ink3">
      <span className={match.match === "meets" ? "text-pos" : "text-ink2"}>
        {MATCH_LABELS[match.match] ?? match.match}
      </span>
      {match.evidence_ref ? ` · ${match.evidence_ref}` : ""} · {match.reason}
    </p>
  );
}

function crossOf(
  assessment: Assessment | null,
  position: number,
): RequirementMatch | null {
  return (
    assessment?.requirement_matches.find(
      (match) => match.requirement_position === position,
    ) ?? null
  );
}

/**
 * El botón de puntuar.
 *
 * Un `<form>` con una acción de servidor y nada de JavaScript propio: la
 * página entera se renderiza en servidor, y esto funciona igual con el
 * navegador sin JS.
 */
function AssessButton({
  captureId,
  label,
}: {
  captureId: string;
  label: string;
}) {
  return (
    <form action={requestAssessment} className="mt-3">
      <input type="hidden" name="capture_id" value={captureId} />
      <button
        type="submit"
        className="rounded border border-acc/40 px-3 py-1.5 font-mono text-xs text-acc hover:bg-acc/10"
      >
        {label}
      </button>
    </form>
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
