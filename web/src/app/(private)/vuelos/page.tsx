import type { Metadata } from "next";
import { leerFecha } from "@/features/vuelos/domain/vuelos";
import { PantallaVuelos } from "@/features/vuelos/ui/pantalla-vuelos";

export const metadata: Metadata = { title: "Vuelos" };

export default async function Vuelos({ searchParams }: PageProps<"/vuelos">) {
  return <PantallaVuelos fecha={leerFecha((await searchParams).fecha)} />;
}
