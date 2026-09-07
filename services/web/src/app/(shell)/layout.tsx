import { Shell } from "@/components/Shell";
import { requireUser } from "@/lib/session";

/**
 * El shell mínimo: navegación persistente para las pantallas que ya
 * existen de verdad. Antes vivía un `requireUser()` repetido en cada
 * página de este grupo; con el layout compartido se pide una sola vez y
 * cubre a todas las rutas de dentro, `/perfil` incluida.
 */
export default async function ShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireUser();

  return <Shell>{children}</Shell>;
}
