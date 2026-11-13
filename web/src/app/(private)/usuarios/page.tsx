import type { Metadata } from "next";
import { PantallaUsuarios } from "@/features/usuarios/ui/pantalla-usuarios";

export const metadata: Metadata = { title: "Usuarios y cargos" };

export default function Usuarios() {
  return <PantallaUsuarios />;
}
