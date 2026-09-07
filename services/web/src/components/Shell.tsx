"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Composición del shell, según `docs/APP_SCREENS.md` §"Estructura del
 * shell" del repositorio privado: barra lateral en escritorio, barra
 * inferior en móvil, mismo orden en las dos porque no hay "Oferta" que
 * intercambiar con "Capturar" todavía.
 *
 * Solo las entradas con pantalla real hoy. El documento describe siete
 * -Hoy, Pipeline, Oferta, CVs y Stats incluidas-, pero cuatro de ellas no
 * tienen ruta construida: añadir un enlace a la nada es peor que no
 * tenerlo. Se completan una a una a medida que su fase construya la
 * pantalla que enlazan.
 */
const NAV_ITEMS = [
  { href: "/ofertas", label: "Pipeline", icon: "▤" },
  { href: "/capturar", label: "Capturar", icon: "＋" },
  { href: "/perfil", label: "Perfil", icon: "◇" },
] as const;

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="md:flex md:min-h-dvh">
      <aside className="hidden shrink-0 flex-col border-r border-white/10 bg-white/[0.02] md:flex md:w-56">
        <div className="flex items-center gap-2 px-5 py-5">
          <span className="text-lg text-acc">◆</span>
          <span className="font-semibold tracking-tight">Futuro</span>
        </div>
        <nav aria-label="Principal" className="flex flex-col gap-1 px-3">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive(pathname, item.href)
                  ? "bg-white/[0.06] text-ink"
                  : "text-ink2 hover:bg-white/[0.03] hover:text-ink"
              }`}
              aria-current={isActive(pathname, item.href) ? "page" : undefined}
            >
              <span
                className={isActive(pathname, item.href) ? "text-acc" : "text-ink3"}
                aria-hidden
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1 pb-16 md:pb-0">{children}</div>

      <nav
        aria-label="Principal (móvil)"
        className="fixed inset-x-0 bottom-0 z-10 flex border-t border-white/10 bg-bg/95 backdrop-blur md:hidden"
      >
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-xs transition-colors ${
              isActive(pathname, item.href) ? "text-acc" : "text-ink2"
            }`}
            aria-current={isActive(pathname, item.href) ? "page" : undefined}
          >
            <span aria-hidden>{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
