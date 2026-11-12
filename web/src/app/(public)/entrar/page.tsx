import type { Metadata } from "next";
import { Suspense } from "react";
import { PantallaEntrar } from "@/features/auth/ui/pantalla-entrar";

export const metadata: Metadata = { title: "Entrar" };

export default function Entrar() {
  return (
    <Suspense>
      <PantallaEntrar />
    </Suspense>
  );
}
