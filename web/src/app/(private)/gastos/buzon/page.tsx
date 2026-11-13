import type { Metadata } from "next";
import { PantallaBuzon } from "@/features/administracion/ui/pantalla-buzon";

export const metadata: Metadata = { title: "Buzón de correo (simulado)" };

export default function Buzon() {
  return <PantallaBuzon />;
}
