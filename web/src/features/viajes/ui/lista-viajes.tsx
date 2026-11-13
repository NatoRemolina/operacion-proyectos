import Link from "next/link";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearRango } from "@/shared/ui/formato";
import { estadoVisibleViaje, type ViajeResumen } from "../domain/viajes";
import { BarraPresupuesto } from "./barra-presupuesto";

/** Lista agrupada sobre una sola superficie, con separadores; toda la fila abre el viaje. */
export function ListaViajes({ viajes, conTitular = false }: { viajes: readonly ViajeResumen[]; conTitular?: boolean }) {
  return (
    <ul
      aria-label="Viajes"
      className="flex flex-col overflow-hidden rounded-tarjeta border border-linea bg-superficie shadow-tarjeta"
    >
      {viajes.map((viaje) => (
        <li key={viaje.id} className="border-b border-linea last:border-b-0">
          <article className="relative px-4 py-4 transition-[background-color] duration-150 hover:bg-neutro-suave focus-within:outline-3 focus-within:-outline-offset-3 focus-within:outline-marca md:px-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-base font-bold tabular-nums">
                  {/* El enlace se estira sobre la fila con ::after para ampliar la zona táctil. */}
                  <Link
                    href={`/viajes/${viaje.id}`}
                    className="after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
                  >
                    {viaje.codigo}
                  </Link>
                </h3>
                <p className="text-base">
                  <span className="sr-only">De {viaje.origen} a {viaje.destino}</span>
                  <span aria-hidden="true" className="font-semibold">
                    {viaje.origen} → {viaje.destino}
                  </span>
                  {conTitular && viaje.titular ? (
                    <span className="text-texto-secundario"> · {viaje.titular.nombre}</span>
                  ) : null}
                </p>
              </div>
              <EtiquetaEstado estado={estadoVisibleViaje(viaje)} texto={viaje.en_curso ? "En curso" : viaje.estado_texto} />
            </div>
            <p className="mt-1 text-sm text-texto-secundario tabular-nums">
              {formatearRango(viaje.ida, viaje.regreso)}
              {viaje.proyecto ? ` · ${viaje.proyecto.nombre}` : ""}
              {` · ${viaje.gastos} ${viaje.gastos === 1 ? "gasto" : "gastos"}`}
            </p>
            <div className="mt-3 max-w-md">
              <BarraPresupuesto
                presupuesto={viaje.presupuesto_usd}
                gastado={viaje.gastado_usd}
                enRevision={viaje.en_revision_usd}
                porcentaje={viaje.ejecucion_pct}
              />
            </div>
          </article>
        </li>
      ))}
    </ul>
  );
}
