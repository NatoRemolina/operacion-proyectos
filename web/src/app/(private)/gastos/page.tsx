import type { Metadata } from "next";
import { PantallaGastos } from "@/features/gastos/ui/pantalla-gastos";

export const metadata: Metadata = { title: "Mis gastos" };

export default function Gastos() {
  return <PantallaGastos />;
}
