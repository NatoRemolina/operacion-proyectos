import Link from "next/link";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearDinero, formatearFecha } from "@/shared/ui/formato";
import { estadoVisibleGasto, siguientePasoGasto, type GastoResumen } from "../domain/gastos";

/**
 * Lista agrupada sobre una sola superficie, con separadores: se recorre de un vistazo y el importe queda siempre en
 * la misma columna. Toda la fila abre el detalle; cada una dice su siguiente paso.
 */
export function ListaGastos({ gastos, esAdmin = false }: { gastos: readonly GastoResumen[]; esAdmin?: boolean }) {
  return (
    <ul
      aria-label="Gastos"
      className="flex flex-col overflow-hidden rounded-tarjeta border border-linea bg-superficie shadow-tarjeta"
    >
      {gastos.map((gasto) => (
        <li key={gasto.id} className="border-b border-linea last:border-b-0">
          <article className="relative grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 px-4 py-4 transition-[background-color] duration-150 hover:bg-neutro-suave focus-within:outline-3 focus-within:-outline-offset-3 focus-within:outline-marca md:px-5">
            <h2 className="text-base font-bold">
              {/* El enlace se estira sobre la fila con ::after para ampliar la zona táctil. */}
              <Link
                href={`/gastos/${gasto.id}`}
                className="text-texto no-underline after:absolute after:inset-0 after:content-[''] hover:text-texto focus-visible:outline-none"
              >
                {gasto.comercio ?? "Comercio por confirmar"}
              </Link>
            </h2>
            <p className="whitespace-nowrap text-right text-base font-bold tabular-nums">
              {formatearDinero(gasto.total, gasto.moneda)}
            </p>
            <p className="text-sm text-texto-secundario tabular-nums">
              {formatearFecha(gasto.fecha)} · {gasto.viaje ? `Viaje ${gasto.viaje.codigo}` : "Sin viaje asignado"}
            </p>
            <p className="flex justify-end">
              <EtiquetaEstado estado={estadoVisibleGasto(gasto.estado)} texto={gasto.estado_texto} />
            </p>
            <p className="col-span-2 text-sm">{siguientePasoGasto(gasto.estado, esAdmin)}</p>
          </article>
        </li>
      ))}
    </ul>
  );
}
