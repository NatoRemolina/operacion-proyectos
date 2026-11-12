import { InsigniaEstado, type Tono } from "@/shared/ui/estado";
import { formatearRango } from "@/shared/ui/formato";
import type { EstadoViaje, ViajeResumen } from "../domain/viajes";
import { BarraPresupuesto } from "./barra-presupuesto";

const TONO: Record<EstadoViaje, Tono> = {
  aprobado: "exito",
  pendiente_aprobacion: "aviso",
  rechazado: "error",
  cerrado: "neutro",
};

export function ListaViajes({ viajes }: { viajes: readonly ViajeResumen[] }) {
  return (
    <ul aria-label="Mis viajes" className="flex flex-col gap-3">
      {viajes.map((viaje) => (
        <li key={viaje.id}>
          <article className="rounded-tarjeta border border-linea bg-superficie p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h3 className="text-lg font-bold">
                  <span className="sr-only">Viaje </span>
                  {viaje.codigo}
                </h3>
                <p className="text-base">
                  <span className="sr-only">De {viaje.origen} a {viaje.destino}</span>
                  <span aria-hidden="true" className="font-semibold">
                    {viaje.origen} → {viaje.destino}
                  </span>
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {viaje.en_curso ? <InsigniaEstado tono="info">En curso</InsigniaEstado> : null}
                <InsigniaEstado tono={TONO[viaje.estado]}>{viaje.estado_texto}</InsigniaEstado>
              </div>
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
