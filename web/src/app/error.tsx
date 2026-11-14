"use client";

import { FalloInesperado } from "@/shared/ui/fallo-inesperado";

/** Un fallo al mostrar cualquier página: mensaje claro, referencia (request_id o digest) y reintentar. */
export default function ErrorDeLaPagina({ error, retry }: { error: unknown; retry: () => void }) {
  return <FalloInesperado error={error} retry={retry} />;
}
