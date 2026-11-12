import type { Metadata } from "next";
import { PantallaNuevoGasto } from "@/features/gastos/ui/pantalla-nuevo-gasto";

export const metadata: Metadata = { title: "Cargar un gasto" };

export default async function NuevoGasto({ searchParams }: PageProps<"/gastos/nuevo">) {
  const { viaje } = await searchParams;
  const viajeInicial = typeof viaje === "string" && /^\d+$/.test(viaje) ? Number(viaje) : undefined;
  return <PantallaNuevoGasto viajeInicial={viajeInicial} />;
}
