import Link from "next/link";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearDinero, formatearFecha } from "@/shared/ui/formato";
import { estadoVisibleGasto, siguientePasoGasto, type GastoResumen } from "../domain/gastos";

/** Tarjetas legibles en celular; toda la tarjeta abre el detalle. Cada una dice su siguiente paso. */
export function ListaGastos({ gastos, esAdmin = false }: { gastos: readonly GastoResumen[]; esAdmin?: boolean }) {
  return (
    <ul aria-label="Gastos" className="flex flex-col gap-3">
      {gastos.map((gasto) => (
        <li key={gasto.id}>
          <article className="relative rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta focus-within:outline-3 focus-within:outline-marca hover:border-borde-campo">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h2 className="text-lg font-bold">
                {/* El enlace se estira sobre la tarjeta con ::after para ampliar la zona táctil. */}
                <Link
                  href={`/gastos/${gasto.id}`}
                  className="text-texto after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
                >
                  {gasto.comercio ?? "Comercio por confirmar"}
                </Link>
              </h2>
              <EtiquetaEstado estado={estadoVisibleGasto(gasto.estado)} texto={gasto.estado_texto} />
            </div>
            <p className="mt-1 text-xl font-bold tabular-nums">{formatearDinero(gasto.total, gasto.moneda)}</p>
            <p className="mt-1 text-sm text-texto-secundario">
              {formatearFecha(gasto.fecha)} · {gasto.viaje ? `Viaje ${gasto.viaje.codigo}` : "Sin viaje asignado"}
            </p>
            <p className="mt-1 text-sm">{siguientePasoGasto(gasto.estado, esAdmin)}</p>
          </article>
        </li>
      ))}
    </ul>
  );
}
