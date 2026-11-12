import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PantallaDetalleViaje } from "@/features/viajes/ui/pantalla-detalle-viaje";

export const metadata: Metadata = { title: "Detalle del viaje" };

export default async function DetalleViaje({ params }: PageProps<"/viajes/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  return <PantallaDetalleViaje id={Number(id)} />;
}
