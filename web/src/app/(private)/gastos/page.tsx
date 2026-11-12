import type { Metadata } from "next";
import type { EstadoGasto } from "@/features/gastos/domain/gastos";
import { PantallaGastos } from "@/features/gastos/ui/pantalla-gastos";

export const metadata: Metadata = { title: "Gastos" };

const ESTADOS: readonly EstadoGasto[] = ["procesando", "revision", "aprobado_auto", "aprobado", "rechazado"];

export default async function Gastos({ searchParams }: PageProps<"/gastos">) {
  const { estado, viaje } = await searchParams;
  return (
    <PantallaGastos
      estado={ESTADOS.find((e) => e === estado)}
      viajeId={typeof viaje === "string" && /^\d+$/.test(viaje) ? Number(viaje) : undefined}
    />
  );
}
