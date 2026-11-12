import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { idDeRuta } from "@/features/cotizar/domain/cotizar";
import { PantallaCotizacion } from "@/features/cotizar/ui/pantalla-cotizacion";

export const metadata: Metadata = { title: "Comparar y decidir" };

export default async function Cotizacion({ params }: PageProps<"/cotizar/[id]">) {
  const { id } = await params;
  const numero = idDeRuta(id);
  if (numero === null) notFound();
  return <PantallaCotizacion id={numero} />;
}
