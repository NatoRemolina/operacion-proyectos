import type { Metadata } from "next";
import { PantallaViajes } from "@/features/viajes/ui/pantalla-viajes";

export const metadata: Metadata = { title: "Mis viajes" };

export default function Viajes() {
  return <PantallaViajes />;
}
