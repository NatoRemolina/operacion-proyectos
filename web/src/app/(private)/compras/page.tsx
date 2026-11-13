import type { Metadata } from "next";
import { PantallaCompras } from "@/features/compras/ui/pantalla-compras";

export const metadata: Metadata = { title: "Compras" };

/** Bandeja de compras (solo administración). El repositorio lo registra la composición de la aplicación. */
export default function Compras() {
  return <PantallaCompras />;
}
