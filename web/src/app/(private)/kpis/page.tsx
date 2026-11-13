import type { Metadata } from "next";
import { leerFiltros } from "@/features/kpis/domain/kpis";
import { PantallaKpis } from "@/features/kpis/ui/pantalla-kpis";

export const metadata: Metadata = { title: "KPIs" };

export default async function Kpis({ searchParams }: PageProps<"/kpis">) {
  return <PantallaKpis filtros={leerFiltros(await searchParams)} />;
}
