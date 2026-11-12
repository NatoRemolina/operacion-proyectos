import type { Metadata } from "next";
import { PantallaResumen } from "@/features/administracion/ui/pantalla-resumen";

export const metadata: Metadata = { title: "Resumen" };

export default function Resumen() {
  return <PantallaResumen />;
}
