import type { Metadata } from "next";
import type { EstadoViaje } from "@/features/viajes/domain/viajes";
import { PantallaViajes } from "@/features/viajes/ui/pantalla-viajes";

export const metadata: Metadata = { title: "Viajes" };

const ESTADOS: readonly EstadoViaje[] = ["pendiente_aprobacion", "aprobado", "rechazado", "cerrado"];

export default async function Viajes({ searchParams }: PageProps<"/viajes">) {
  const { estado } = await searchParams;
  const filtro = ESTADOS.find((e) => e === estado);
  return <PantallaViajes estado={filtro} />;
}
