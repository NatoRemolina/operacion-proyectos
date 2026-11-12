import type { Metadata } from "next";
import { PantallaNuevoGasto } from "@/features/gastos/ui/pantalla-nuevo-gasto";

export const metadata: Metadata = { title: "Enviar recibo" };

export default function NuevoGasto() {
  return <PantallaNuevoGasto />;
}
