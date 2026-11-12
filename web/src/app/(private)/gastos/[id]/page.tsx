import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PantallaDetalleGasto } from "@/features/gastos/ui/pantalla-detalle-gasto";

export const metadata: Metadata = { title: "Detalle del gasto" };

export default async function DetalleGasto({ params }: PageProps<"/gastos/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  return <PantallaDetalleGasto id={Number(id)} />;
}
