import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "futuro-app",
  description: "De una oferta de trabajo a una candidatura lista para enviar.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
