import type { ReactNode } from "react";
import { InsigniaEstado } from "@/shared/ui/estado";
import { formatearValor, textoMeta, tonoDeEstado, type EstadoKpi, type Kpi, type Par } from "../domain/kpis";

export const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

const BORDE: Record<EstadoKpi, string> = {
  verde: "border-l-exito",
  ambar: "border-l-aviso",
  rojo: "border-l-error",
  "sin datos": "border-l-neutro",
  "fuera de rango": "border-l-aviso",
};

export function SemaforoKpi({ estado, children }: { estado: EstadoKpi; children: ReactNode }) {
  return <InsigniaEstado tono={tonoDeEstado(estado)}>{children}</InsigniaEstado>;
}

/** Un indicador: cifra, semáforo con texto, meta, responsable, para qué sirve y cómo se calcula. */
export function TarjetaKpi({ kpi }: { kpi: Kpi }) {
  return (
    <article
      aria-labelledby={`kpi-${kpi.nombre}`}
      className={`flex min-w-0 flex-col gap-2 rounded-tarjeta border border-l-4 border-linea bg-superficie p-4 shadow-tarjeta ${BORDE[kpi.estado]}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 id={`kpi-${kpi.nombre}`} className="min-w-0 font-bold">
          {kpi.titulo}
        </h3>
        <SemaforoKpi estado={kpi.estado}>{kpi.estado_texto}</SemaforoKpi>
      </div>
      <p className="text-cifra font-bold tabular-nums">
        {/* Sin valor el semáforo ya dice «Sin datos»: la cifra no lo repite. */}
        {kpi.valor === null ? <span aria-label="Sin valor">—</span> : formatearValor(kpi.valor, kpi.unidad)}
      </p>
      <p className="text-sm text-texto-secundario">
        {textoMeta(kpi)} · {kpi.responsable}
      </p>
      {kpi.estado === "fuera de rango" ? (
        <p className="text-sm font-semibold text-aviso">
          Este valor no es posible para el indicador: revisa los datos de origen (por ejemplo, fechas futuras).
        </p>
      ) : null}
      <p className="text-sm text-texto-secundario">Sirve para: {kpi.para_que}</p>
      <details className="text-sm">
        <summary className="min-h-11 cursor-pointer content-center font-semibold">Cómo se calcula</summary>
        <p className="text-texto-secundario">
          {kpi.formula}. Nombre en la API: <code>{kpi.nombre}</code>.
        </p>
      </details>
    </article>
  );
}

/** Tabla de dos columnas para los desgloses (etiqueta y cifra). */
export function TablaPares({
  titulo,
  pares,
  columnas,
  vacio = "Sin datos en el periodo.",
}: {
  titulo: string;
  pares: readonly Par[];
  columnas: readonly [string, string];
  vacio?: string;
}) {
  return (
    <section className={TARJETA} aria-label={titulo}>
      <h3 className="font-bold">{titulo}</h3>
      {pares.length === 0 ? (
        <p className="mt-2 text-texto-secundario">{vacio}</p>
      ) : (
        <table className="mt-2 w-full text-left">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-texto-secundario">
              <th scope="col" className="py-2">
                {columnas[0]}
              </th>
              <th scope="col" className="py-2 text-right">
                {columnas[1]}
              </th>
            </tr>
          </thead>
          <tbody>
            {pares.map((p, i) => (
              <tr key={`${p.etiqueta}-${i}`} className="border-t border-linea">
                <td className="break-words py-2 pr-3">{p.etiqueta ?? "—"}</td>
                <td className="py-2 text-right tabular-nums">{p.valor ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/**
 * Tabla simple con desplazamiento propio: en celular la tabla se desliza dentro de su tarjeta
 * y la página nunca se desplaza de lado.
 */
export function TablaSimple({
  titulo,
  encabezados,
  filas,
  vacio,
  nota,
}: {
  titulo: string;
  encabezados: readonly { texto: string; fin?: boolean }[];
  filas: readonly { clave: string | number; celdas: readonly ReactNode[] }[];
  vacio: string;
  nota?: ReactNode;
}) {
  return (
    <section className={`${TARJETA} min-w-0`} aria-label={titulo}>
      <h3 className="font-bold">{titulo}</h3>
      {nota ? <p className="mt-1 text-sm text-texto-secundario">{nota}</p> : null}
      {filas.length === 0 ? (
        <p className="mt-2 text-texto-secundario">{vacio}</p>
      ) : (
        <div className="mt-2 overflow-x-auto" tabIndex={0} role="region" aria-label={`${titulo} (se desliza de lado)`}>
          <table className="w-full text-left">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-texto-secundario">
                {encabezados.map((e) => (
                  <th key={e.texto} scope="col" className={`whitespace-nowrap py-2 pr-3 ${e.fin ? "text-right" : ""}`}>
                    {e.texto}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.clave} className="border-t border-linea">
                  {f.celdas.map((c, i) => (
                    <td key={i} className={`py-2 pr-3 align-top ${encabezados[i]?.fin ? "text-right tabular-nums whitespace-nowrap" : ""}`}>
                      {c}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function usd(valor: number | null): string {
  return formatearValor(valor, "USD");
}

export function pct(valor: number | null): string {
  return valor === null ? "—" : formatearValor(valor, "%");
}
