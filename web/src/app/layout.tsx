import type { Metadata, Viewport } from "next";
import { Mulish } from "next/font/google";
import { connection } from "next/server";
import { Proveedores } from "@/composition/proveedores";
import { leerFuenteDatos } from "@/config/configuracion";
import "./globals.css";

// La fuente se descarga al compilar y se sirve desde la propia web: sin peticiones a terceros.
const mulish = Mulish({ subsets: ["latin"], variable: "--font-mulish", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Plataforma de viajes y gastos", template: "%s · Viajes y gastos" },
  description: "Consulta tus viajes, envía recibos y sigue su estado.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // FUENTE_DATOS se lee en cada petición (no al compilar): la misma imagen sirve para demo y real.
  await connection();
  const fuente = leerFuenteDatos(process.env.FUENTE_DATOS);
  return (
    <html lang="es" className={`${mulish.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <Proveedores fuente={fuente}>{children}</Proveedores>
      </body>
    </html>
  );
}
