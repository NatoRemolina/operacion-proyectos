import { formatearDinero } from "@/shared/ui/formato";
import type { Dinero } from "@/shared/domain/tipos";

/** Ejecución del presupuesto: la cifra y el porcentaje van escritos; la barra solo acompaña. */
export function BarraPresupuesto({
  presupuesto,
  gastado,
  enRevision,
  porcentaje,
}: {
  presupuesto: Dinero;
  gastado: Dinero;
  enRevision: Dinero;
  porcentaje: number | null;
}) {
  if (presupuesto === null || porcentaje === null) {
    return (
      <p className="text-sm text-texto-secundario">
        Sin presupuesto asignado. Gastado: {formatearDinero(gastado ?? "0.00")}.
      </p>
    );
  }
  const excedido = porcentaje > 100;
  const alto = !excedido && porcentaje >= 85;
  const color = excedido ? "bg-error" : alto ? "bg-aviso" : "bg-marca";
  const hayRevision = enRevision !== null && Number(enRevision) > 0;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-sm">
        <span className="font-semibold">
          {formatearDinero(gastado ?? "0.00")} de {formatearDinero(presupuesto)}
        </span>{" "}
        <span className="text-texto-secundario">({porcentaje} %)</span>
        {excedido ? (
          <strong className="ml-1 text-error">
            <span aria-hidden="true">✕ </span>sobre el presupuesto
          </strong>
        ) : null}
      </p>
      <div aria-hidden="true" className="h-2.5 w-full overflow-hidden rounded-full bg-neutro-suave">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(porcentaje, 100)}%` }} />
      </div>
      {hayRevision ? (
        <p className="text-sm text-texto-secundario">
          Además, {formatearDinero(enRevision)} en revisión.
        </p>
      ) : null}
    </div>
  );
}
