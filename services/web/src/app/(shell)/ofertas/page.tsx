import Link from "next/link";

import { State } from "@/components/State";
import type {
  ApplicationStatus,
  OfferSortField,
  OfferSortOrder,
  OfferSummary,
} from "@/lib/api";
import { listOffers } from "@/lib/api";
import {
  APPLICATION_STATUSES,
  APPLICATION_STATUS_LABELS,
  ASSESSMENT_STATUS_LABELS,
  PORTFOLIO_LABELS,
  POSTING_STATUS_LABELS,
  PROBABILITY_LABELS,
  STATUS_LABELS,
} from "@/lib/labels";

export const dynamic = "force-dynamic";

const POSTING_STATUSES = ["active_verified", "expired", "unverifiable"] as const;
const PORTFOLIO_BUCKETS = [
  "realistic",
  "realistic_stretch",
  "aspirational",
  "experimental",
  "discard",
] as const;

type Filters = {
  status?: ApplicationStatus;
  posting_status?: string;
  portfolio_bucket?: string;
  sort: OfferSortField;
  order: OfferSortOrder;
};

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * La pantalla Pipeline de `docs/APP_SCREENS.md` (repositorio privado), en su
 * vista de tabla densa -mapa valor × probabilidad y kanban son las
 * rebanadas 3 y 4, no esta-.
 *
 * Sin selector de vistas ni buscador de texto libre, y sin paginación por
 * cursor: micro-decisiones acordadas con Pablo el 2026-09-13, ver
 * `NEXT_SESSION.md`. Orden y filtro viajan en la URL (`searchParams`) y no
 * en estado de cliente: las cabeceras de columna y las opciones de filtro
 * son enlaces normales, sin una sola línea de JavaScript propio.
 */
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters: Filters = {
    status: first(params.status) as ApplicationStatus | undefined,
    posting_status: first(params.posting_status),
    portfolio_bucket: first(params.portfolio_bucket),
    sort: (first(params.sort) as OfferSortField | undefined) ?? "captured_at",
    order: (first(params.order) as OfferSortOrder | undefined) ?? "desc",
  };

  const offers = await listOffers(filters);

  const hrefFor = (overrides: Partial<Filters>) => {
    const merged = { ...filters, ...overrides };
    const query = new URLSearchParams();
    if (merged.status) query.set("status", merged.status);
    if (merged.posting_status) query.set("posting_status", merged.posting_status);
    if (merged.portfolio_bucket) {
      query.set("portfolio_bucket", merged.portfolio_bucket);
    }
    if (merged.sort !== "captured_at") query.set("sort", merged.sort);
    if (merged.order !== "desc") query.set("order", merged.order);
    const qs = query.toString();
    return qs ? `/ofertas?${qs}` : "/ofertas";
  };

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-6 py-12">
      <header className="flex items-end justify-between gap-4">
        <div className="space-y-2">
          <p className="font-mono text-xs uppercase tracking-widest text-ink3">
            Pipeline
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Ofertas</h1>
        </div>
        <Link
          href="/capturar"
          className="rounded-md bg-acc px-3 py-1.5 text-sm font-medium text-bg transition-opacity hover:opacity-90"
        >
          Pegar una oferta
        </Link>
      </header>

      <FilterBar filters={filters} hrefFor={hrefFor} />

      {offers === null ? (
        <p className="font-mono text-sm text-neg">▲ La API no responde.</p>
      ) : offers.length === 0 ? (
        <p className="text-sm text-ink2">Ninguna oferta cumple estos filtros.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-white/10">
          <table className="w-full min-w-[880px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-white/10 font-mono text-xs uppercase tracking-widest text-ink3">
                <Th>
                  <SortLink field="title" label="Puesto" filters={filters} hrefFor={hrefFor} />
                  {" · "}
                  <SortLink field="company" label="Empresa" filters={filters} hrefFor={hrefFor} />
                </Th>
                <Th>Candidatura</Th>
                <Th align="right">
                  <SortLink field="value_score" label="Valor" filters={filters} hrefFor={hrefFor} />
                </Th>
                <Th>Probabilidad</Th>
                <Th>Cartera</Th>
                <Th>Anuncio</Th>
                <Th>
                  <SortLink field="captured_at" label="Capturada" filters={filters} hrefFor={hrefFor} />
                </Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {offers.map((offer) => (
                <Row key={offer.id} offer={offer} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th className={`px-4 py-3 font-medium ${align === "right" ? "text-right" : "text-left"}`}>
      {children}
    </th>
  );
}

/** Una cabecera de columna, como enlace que ordena por esa columna. */
function SortLink({
  field,
  label,
  filters,
  hrefFor,
}: {
  field: OfferSortField;
  label: string;
  filters: Filters;
  hrefFor: (overrides: Partial<Filters>) => string;
}) {
  const isActive = filters.sort === field;
  const nextOrder: OfferSortOrder = isActive && filters.order === "asc" ? "desc" : "asc";
  return (
    <Link
      href={hrefFor({ sort: field, order: nextOrder })}
      className={isActive ? "text-acc" : "hover:text-ink1"}
    >
      {label}
      {isActive ? (filters.order === "asc" ? " ↑" : " ↓") : ""}
    </Link>
  );
}

/**
 * Los tres filtros estructurados de esta rebanada -sin buscador de texto
 * libre, a propósito-. Cada opción es un enlace: cambia el filtro y
 * conserva el orden y los demás filtros vigentes.
 */
function FilterBar({
  filters,
  hrefFor,
}: {
  filters: Filters;
  hrefFor: (overrides: Partial<Filters>) => string;
}) {
  return (
    <div className="space-y-1.5 font-mono text-xs">
      <FilterRow
        label="Candidatura"
        current={filters.status}
        options={APPLICATION_STATUSES.map((value) => ({
          value,
          label: APPLICATION_STATUS_LABELS[value],
        }))}
        hrefFor={(value) => hrefFor({ status: value as ApplicationStatus | undefined })}
      />
      <FilterRow
        label="Anuncio"
        current={filters.posting_status}
        options={POSTING_STATUSES.map((value) => ({
          value,
          label: POSTING_STATUS_LABELS[value] ?? value,
        }))}
        hrefFor={(value) => hrefFor({ posting_status: value })}
      />
      <FilterRow
        label="Cartera"
        current={filters.portfolio_bucket}
        options={PORTFOLIO_BUCKETS.map((value) => ({
          value,
          label: PORTFOLIO_LABELS[value] ?? value,
        }))}
        hrefFor={(value) => hrefFor({ portfolio_bucket: value })}
      />
    </div>
  );
}

function FilterRow({
  label,
  current,
  options,
  hrefFor,
}: {
  label: string;
  current: string | undefined;
  options: { value: string; label: string }[];
  hrefFor: (value: string | undefined) => string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="text-ink3">{label}</span>
      <Link
        href={hrefFor(undefined)}
        className={!current ? "text-acc" : "text-ink2 hover:text-ink1"}
      >
        todas
      </Link>
      {options.map((option) => (
        <Link
          key={option.value}
          href={hrefFor(option.value)}
          className={current === option.value ? "text-acc" : "text-ink2 hover:text-ink1"}
        >
          {option.label}
        </Link>
      ))}
    </div>
  );
}

function Row({ offer }: { offer: OfferSummary }) {
  return (
    <tr className="transition-colors hover:bg-white/[0.03]">
      <td className="max-w-[16rem] px-4 py-3">
        <Link href={`/ofertas/${offer.id}`} className="block min-w-0">
          <span className="block truncate text-sm">
            {offer.title ?? (
              <span className="text-ink3">
                {STATUS_LABELS[offer.extraction_status] ?? offer.extraction_status}
              </span>
            )}
          </span>
          <span className="block truncate text-xs text-ink3">
            {offer.company ?? "—"}
          </span>
        </Link>
      </td>
      <td className="px-4 py-3">
        <State value={APPLICATION_STATUS_LABELS[offer.status]} tone="acc" />
      </td>
      <td className="px-4 py-3 text-right font-mono">
        {offer.value_score !== null ? (
          <span className="text-base font-semibold">{offer.value_score}</span>
        ) : (
          <span className="text-xs text-ink3">
            {ASSESSMENT_STATUS_LABELS[offer.assessment_status] ??
              offer.assessment_status}
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        {offer.probability_band ? (
          <State
            value={PROBABILITY_LABELS[offer.probability_band] ?? offer.probability_band}
            tone="acc"
          />
        ) : (
          <span className="text-xs text-ink3">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        {offer.portfolio_bucket ? (
          <State
            value={PORTFOLIO_LABELS[offer.portfolio_bucket] ?? offer.portfolio_bucket}
            tone="pos"
          />
        ) : (
          <span className="text-xs text-ink3">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-ink2">
        {offer.posting_status
          ? (POSTING_STATUS_LABELS[offer.posting_status] ?? offer.posting_status)
          : "—"}
      </td>
      <td className="px-4 py-3 font-mono text-xs text-ink3">
        {new Date(offer.captured_at).toLocaleDateString("es-ES")}
      </td>
    </tr>
  );
}
