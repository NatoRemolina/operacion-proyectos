import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PantallaFichaPersona } from "@/features/kpis/ui/pantalla-ficha-persona";

export const metadata: Metadata = { title: "Ficha de la persona" };

export default async function FichaPersona({ params }: PageProps<"/kpis/persona/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id) || Number(id) < 1) notFound();
  return <PantallaFichaPersona id={Number(id)} />;
}
