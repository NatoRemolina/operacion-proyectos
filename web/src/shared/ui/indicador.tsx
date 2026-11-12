import type { ReactNode } from "react";

/** Indicador del diseño: etiqueta pequeña, cifra grande y una línea de contexto. */
export function Indicador({ etiqueta, cifra, pie }: { etiqueta: string; cifra: ReactNode; pie?: ReactNode }) {
  return (
    <div className="rounded-tarjeta border border-linea bg-superficie p-4 shadow-sm">
      <dt className="text-sm text-texto-secundario">{etiqueta}</dt>
      <dd className="mt-1 text-2xl font-bold tabular-nums">{cifra}</dd>
      {pie ? <dd className="mt-1 text-sm text-texto-secundario">{pie}</dd> : null}
    </div>
  );
}
