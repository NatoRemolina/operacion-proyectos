import { formatearDinero } from "@/shared/ui/formato";
import { Indicador } from "@/shared/ui/indicador";
import type { ViajeResumen } from "../domain/viajes";

/** Cifras del viaje en curso, tal como las calcula la API. */
export function ResumenViajeEnCurso({ viaje }: { viaje: ViajeResumen }) {
  return (
    <section aria-labelledby="titulo-en-curso">
      <h2 id="titulo-en-curso" className="mb-2 text-lg font-bold">
        Viaje en curso: {viaje.codigo}
      </h2>
      <dl className="grid gap-3 sm:grid-cols-3">
        <Indicador
          etiqueta="Presupuesto aprobado"
          cifra={viaje.presupuesto_usd === null ? "Sin presupuesto" : formatearDinero(viaje.presupuesto_usd)}
          pie={`${viaje.origen} → ${viaje.destino}`}
        />
        <Indicador
          etiqueta="Gastado"
          cifra={formatearDinero(viaje.gastado_usd ?? "0.00")}
          pie={viaje.ejecucion_pct === null ? "Sin porcentaje" : `${viaje.ejecucion_pct} % del presupuesto`}
        />
        <Indicador
          etiqueta="En revisión"
          cifra={formatearDinero(viaje.en_revision_usd ?? "0.00")}
          pie="Administración lo revisa"
        />
      </dl>
    </section>
  );
}
