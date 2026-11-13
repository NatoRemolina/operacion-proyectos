import type { Metadata } from "next";
import { PantallaProyectos } from "@/features/proyectos/ui/pantalla-proyectos";

export const metadata: Metadata = { title: "Proyectos" };

export default function Proyectos() {
  return <PantallaProyectos />;
}
