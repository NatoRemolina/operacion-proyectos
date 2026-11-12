import type { ReactNode } from "react";

export type TonoDistintivo = "marca" | "exito" | "aviso" | "neutro";

const ESTILOS: Record<TonoDistintivo, string> = {
  marca: "border-marca bg-marca-suave text-marca",
  exito: "border-exito bg-exito-suave text-exito",
  aviso: "border-aviso bg-aviso-suave text-aviso",
  neutro: "border-neutro bg-neutro-suave text-neutro",
};

/**
 * Etiqueta corta junto a un dato (origen del precio, «Google», «Recomendada»). Siempre con texto. No es un estado:
 * para estados está `EtiquetaEstado`.
 */
export function Distintivo({ tono = "neutro", children }: { tono?: TonoDistintivo; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-bold ${ESTILOS[tono]}`}>
      {children}
    </span>
  );
}
