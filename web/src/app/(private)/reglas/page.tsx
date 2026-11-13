import type { Metadata } from "next";
import { PantallaReglas } from "@/features/reglas/ui/pantalla-reglas";

export const metadata: Metadata = { title: "Reglas y supuestos" };

export default function Reglas() {
  return <PantallaReglas />;
}
