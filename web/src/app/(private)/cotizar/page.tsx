import type { Metadata } from "next";
import { PantallaCotizar } from "@/features/cotizar/ui/pantalla-cotizar";

export const metadata: Metadata = { title: "Cotizar un viaje" };

export default function Cotizar() {
  return <PantallaCotizar />;
}
