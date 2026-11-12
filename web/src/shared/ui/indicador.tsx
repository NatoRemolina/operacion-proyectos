import type { ReactNode } from "react";

/** Grupo de tarjetas de indicador. Es una lista de definiciones con nombre propio. */
export function Indicadores({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <dl role="group" aria-label={etiqueta} className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {children}
    </dl>
  );
}

/** Tarjeta de indicador del diseño: etiqueta pequeña, cifra grande y una línea de contexto. */
export function Indicador({
  etiqueta,
  cifra,
  pie,
  destacado = false,
}: {
  etiqueta: string;
  cifra: ReactNode;
  pie?: ReactNode;
  /** El indicador que pide atención (por ejemplo, viajes por aprobar): borde de marca. */
  destacado?: boolean;
}) {
  return (
    <div
      className={`rounded-tarjeta border bg-superficie p-4 shadow-tarjeta ${destacado ? "border-marca" : "border-linea"}`}
    >
      <dt className="text-sm text-texto-secundario">{etiqueta}</dt>
      <dd className="mt-1 text-cifra font-bold tabular-nums">{cifra}</dd>
      {pie ? <dd className="mt-1 text-sm text-texto-secundario">{pie}</dd> : null}
    </div>
  );
}
