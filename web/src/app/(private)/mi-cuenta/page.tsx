import type { Metadata } from "next";
import { PantallaMiCuenta } from "@/features/cuenta/ui/pantalla-mi-cuenta";

export const metadata: Metadata = { title: "Mi cuenta" };

export default function MiCuenta() {
  return <PantallaMiCuenta />;
}
