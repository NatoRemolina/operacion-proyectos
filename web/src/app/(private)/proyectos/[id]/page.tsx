import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PantallaTableroProyecto } from "@/features/proyectos/ui/pantalla-tablero-proyecto";

export const metadata: Metadata = { title: "Tablero del proyecto" };

export default async function TableroProyecto({ params }: PageProps<"/proyectos/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  return <PantallaTableroProyecto id={Number(id)} />;
}
