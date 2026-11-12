import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PantallaCotizacion } from "@/features/cotizar/ui/pantalla-cotizacion";

export const metadata: Metadata = { title: "Comparar y decidir" };

export default async function Cotizacion({ params }: PageProps<"/cotizar/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  return <PantallaCotizacion id={Number(id)} />;
}
