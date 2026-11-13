import type { Metadata } from "next";
import { leerFiltros } from "@/features/kpis/domain/kpis";
import { leerPestana } from "@/features/monitoreo/domain/monitoreo";
import { PantallaMonitoreo } from "@/features/monitoreo/ui/pantalla-monitoreo";

export const metadata: Metadata = { title: "Monitoreo" };

export default async function Monitoreo({ searchParams }: PageProps<"/monitoreo">) {
  const parametros = await searchParams;
  return <PantallaMonitoreo pestana={leerPestana(parametros.pestana)} filtros={leerFiltros(parametros)} />;
}
