import type { ReactNode } from "react";
import { Alerta } from "@/shared/ui/estado";
import { formatearDinero, formatearFecha, formatearInstante } from "@/shared/ui/formato";
import type { GastoDetalle } from "../domain/gastos";
import { InsigniaGasto } from "./estado-gasto";

const CANAL: Record<string, string> = {
  web: "Web",
  celular: "Celular",
  correo: "Correo",
  telegram: "Telegram",
};

function Fila({ termino, children }: { termino: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-4 border-b border-linea py-2 last:border-b-0">
      <dt className="text-texto-secundario">{termino}</dt>
      <dd className="text-right font-semibold tabular-nums">{children}</dd>
    </div>
  );
}

export function DetalleGasto({
  gasto,
  urlOriginal,
}: {
  gasto: GastoDetalle;
  urlOriginal: string | null;
}) {
  const moneda = gasto.moneda;
  return (
    <article aria-labelledby="titulo-gasto" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 id="titulo-gasto" className="text-2xl font-extrabold">
          {gasto.comercio ?? "Gasto sin comercio leído"}
        </h1>
        <InsigniaGasto estado={gasto.estado} texto={gasto.estado_texto} />
      </div>

      {gasto.estado === "revision" ? (
        <Alerta
          tono="aviso"
          titulo={
            !(gasto.puede_justificar ?? true)
              ? "En revisión: administración lo revisa."
              : gasto.justificaciones.length
                ? "En revisión: administración lo revisa con lo que contaste."
                : "En revisión: administración lo revisa. Si cuentas abajo para qué fue, se resuelve antes."
          }
        />
      ) : null}

      {gasto.estado === "rechazado" ? (
        <Alerta tono="error" titulo="Por qué se rechazó">
          <p>{gasto.motivo_rechazo || "Quien revisó no dejó el motivo escrito."}</p>
        </Alerta>
      ) : null}

      {gasto.alertas.length > 0 ? (
        <section aria-labelledby="titulo-alertas">
          <h2 id="titulo-alertas" className="mb-2 text-lg font-bold">
            Observaciones
          </h2>
          <ul className="flex flex-col gap-2">
            {gasto.alertas.map((alerta) => (
              <li key={alerta} className="rounded-lg border-l-4 border-aviso bg-aviso-suave p-3">
                <span aria-hidden="true" className="font-bold text-aviso">
                  !{" "}
                </span>
                {alerta}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-labelledby="titulo-datos" className="rounded-tarjeta border border-linea bg-superficie p-4">
        <h2 id="titulo-datos" className="mb-1 text-lg font-bold">
          Datos del recibo
        </h2>
        <dl>
          <Fila termino="Fecha">{formatearFecha(gasto.fecha)}</Fila>
          <Fila termino="Categoría">{gasto.categoria ?? "Por confirmar"}</Fila>
          <Fila termino="Subtotal">{formatearDinero(gasto.subtotal, moneda)}</Fila>
          <Fila termino="Impuesto">{formatearDinero(gasto.impuesto, moneda)}</Fila>
          <Fila termino="Propina">
            {gasto.propina === null ? "Sin propina" : formatearDinero(gasto.propina, moneda)}
          </Fila>
          <Fila termino="Total">{formatearDinero(gasto.total, moneda)}</Fila>
          {moneda && moneda !== "USD" ? (
            <Fila termino="Total en dólares">{formatearDinero(gasto.total_usd, "USD")}</Fila>
          ) : null}
          <Fila termino="Viaje">{gasto.viaje?.codigo ?? "Sin viaje asignado"}</Fila>
          <Fila termino="Enviado por">{CANAL[gasto.canal] ?? gasto.canal}</Fila>
          <Fila termino="Recibido">{formatearInstante(gasto.creado)}</Fila>
        </dl>
      </section>

      <section aria-labelledby="titulo-original">
        <h2 id="titulo-original" className="mb-1 text-lg font-bold">
          Recibo original
        </h2>
        {gasto.documento_id === null ? (
          <p className="text-texto-secundario">Este gasto no tiene un archivo original guardado.</p>
        ) : urlOriginal ? (
          <a href={urlOriginal} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center">
            Ver el recibo original (se abre en otra pestaña)
          </a>
        ) : (
          <p className="text-texto-secundario">El original no está disponible en esta fuente de datos.</p>
        )}
      </section>
    </article>
  );
}
