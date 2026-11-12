import Link from "next/link";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearRango } from "@/shared/ui/formato";
import { estadoVisibleViaje, type ViajeResumen } from "../domain/viajes";
import { BarraPresupuesto } from "./barra-presupuesto";

export function ListaViajes({ viajes, conTitular = false }: { viajes: readonly ViajeResumen[]; conTitular?: boolean }) {
  return (
    <ul aria-label="Viajes" className="flex flex-col gap-3">
      {viajes.map((viaje) => (
        <li key={viaje.id}>
          <article className="rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="text-lg font-bold">
                  <Link href={`/viajes/${viaje.id}`}>{viaje.codigo}</Link>
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
            <p className="mt-1 text-sm text-texto-secundario">
              {formatearRango(viaje.ida, viaje.regreso)}
              {viaje.proyecto ? ` · ${viaje.proyecto.nombre}` : ""}
              {` · ${viaje.gastos} ${viaje.gastos === 1 ? "gasto" : "gastos"}`}
            </p>
            <div className="mt-3">
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
