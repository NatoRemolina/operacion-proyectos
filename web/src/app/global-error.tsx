"use client";

import { FalloInesperado } from "@/shared/ui/fallo-inesperado";
import "./globals.css";

/** Un fallo en la plantilla raíz: reemplaza el documento entero, por eso trae su `<html>` y sus estilos. */
export default function ErrorGlobal({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <html lang="es" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <title>Algo falló · Inflight</title>
        <FalloInesperado error={error} retry={retry} />
      </body>
    </html>
  );
}
