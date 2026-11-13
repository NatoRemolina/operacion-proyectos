"use client";

import { Alerta } from "@/shared/ui/estado";
import { formatearDinero, formatearInstante } from "@/shared/ui/formato";
import { useEvidencia } from "../application/cotizar";
import type { CapturaEvidencia, Evidencia } from "../domain/cotizar";

const MOTIVO: Record<CapturaEvidencia["motivo"], string> = {
  decision: "al decidir",
  seguimiento: "seguimiento diario",
  compra: "al comprar",
};
const TIPO: Record<CapturaEvidencia["tipo"], string> = { vuelo: "vuelo", hotel: "hotel" };

/** «21:12» en la hora de quien mira. */
function horaLocal(iso: string): string {
  const fecha = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(fecha.getTime())) return iso.slice(11, 16);
  return new Intl.DateTimeFormat("es-CO", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(fecha);
}

function dinero(valor: unknown): string | null {
  return typeof valor === "number" && Number.isFinite(valor) ? formatearDinero(valor.toFixed(2)) : null;
}

function objeto(valor: unknown): Record<string, unknown> {
  return valor && typeof valor === "object" && !Array.isArray(valor) ? (valor as Record<string, unknown>) : {};
}

/** Lo esencial de lo leído, en frases; el detalle completo va debajo, plegado. */
function resumen(c: CapturaEvidencia): string[] {
  const datos = objeto(c.datos);
  const lineas: string[] = [];
  const aerolinea = objeto(datos.aerolinea);
  if (dinero(aerolinea.total)) lineas.push(`Total en la aerolínea: ${dinero(aerolinea.total)}`);
  if (dinero(aerolinea.impuestos)) lineas.push(`Impuestos: ${dinero(aerolinea.impuestos)}`);
  if (Array.isArray(aerolinea.numeros) && aerolinea.numeros.length) lineas.push(`Vuelos: ${aerolinea.numeros.join(", ")}`);
  if (typeof aerolinea.fallo === "string") lineas.push(`Aerolínea: ${aerolinea.fallo}`);
  const google = objeto(datos.google);
  if (dinero(google.precio_total)) lineas.push(`Precio en Google Flights: ${dinero(google.precio_total)}`);
  const hotel = objeto(datos.hotel);
  if (typeof hotel.nombre === "string") lineas.push(hotel.nombre);
  if (typeof hotel.calificacion === "number") {
    lineas.push(`Calificación ${hotel.calificacion}${typeof hotel.resenas === "number" ? ` (${hotel.resenas} reseñas)` : ""}`);
  }
  return lineas;
}

function Captura({ c }: { c: CapturaEvidencia }) {
  const titulo = `Captura del ${TIPO[c.tipo]} (${MOTIVO[c.motivo]})`;
  if (c.estado !== "lista") {
    return (
      <li className="text-sm text-texto-secundario">
        {titulo}: {c.estado === "fallida" ? `no se pudo guardar${c.fallo ? ` (${c.fallo})` : ""}` : "en cola"}
      </li>
    );
  }
  return (
    <li className="flex flex-col gap-2">
      <p className="font-semibold">
        {titulo}
        {c.terminado ? <span className="font-normal text-texto-secundario"> · {formatearInstante(c.terminado)}</span> : null}
      </p>
      <ul className="text-sm">
        {resumen(c).map((linea) => (
          <li key={linea}>{linea}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-3 text-sm">
        {c.imagenes.map((url, n) => (
          <a key={url} href={url} target="_blank" rel="noopener noreferrer" className="underline">
            Captura de página completa {n + 1} del {TIPO[c.tipo]}
          </a>
        ))}
        {c.texto_url ? (
          <a href={c.texto_url} target="_blank" rel="noopener noreferrer" className="underline">
            Texto completo del {TIPO[c.tipo]}
          </a>
        ) : null}
      </div>
      {c.datos ? (
        <details className="text-sm">
          <summary className="cursor-pointer">Detalle completo de lo leído</summary>
          <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-tarjeta bg-fondo p-3 text-xs">
            {JSON.stringify(c.datos, null, 2)}
          </pre>
        </details>
      ) : null}
    </li>
  );
}

/** La evidencia de la decisión (pieza 5): mientras se guarda, lo dice; guardada, las capturas y el seguimiento. */
export function EvidenciaGuardada({ evidencia }: { evidencia: Evidencia }) {
  if (evidencia.estado === "sin_evidencia" && !evidencia.capturas.length) return null;
  if (evidencia.estado === "guardando" && !evidencia.guardada) {
    return (
      <p role="status" className="text-sm text-texto-secundario">
        Guardando la evidencia del vuelo…
      </p>
    );
  }
  const titulo = evidencia.guardada ? `Evidencia guardada a las ${horaLocal(evidencia.guardada)}` : "Evidencia de la decisión";
  return (
    <section aria-label={titulo} className="flex flex-col gap-3 rounded-tarjeta border border-borde-campo p-4">
      <h3 className="font-bold">{titulo}</h3>
      {evidencia.estado === "guardando" ? (
        <p role="status" className="text-sm text-texto-secundario">
          Guardando la evidencia del vuelo…
        </p>
      ) : null}
      <ul className="flex flex-col gap-4">
        {evidencia.capturas.map((c) => (
          <Captura key={c.id} c={c} />
        ))}
      </ul>
      {evidencia.seguimiento.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" aria-label="Precios del seguimiento">
            <thead>
              <tr>
                <th scope="col" className="py-1 pr-3">Cuándo</th>
                <th scope="col" className="py-1 pr-3">Google Flights</th>
                <th scope="col" className="py-1">Aerolínea (con impuestos)</th>
              </tr>
            </thead>
            <tbody>
              {evidencia.seguimiento.map((p, i) => (
                <tr key={`${p.momento}-${i}`}>
                  <td className="py-1 pr-3">
                    {p.momento ? formatearInstante(p.momento) : "—"} · {MOTIVO[p.motivo]}
                  </td>
                  <td className="py-1 pr-3">{p.precio_google_usd ? formatearDinero(p.precio_google_usd) : "—"}</td>
                  <td className="py-1">{p.total_aerolinea_usd ? formatearDinero(p.total_aerolinea_usd) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

/** La evidencia de una cotización decidida, con su consulta (se sigue mientras se guarda). */
export function EvidenciaDeCotizacion({ id }: { id: number }) {
  const consulta = useEvidencia(id, true);
  if (consulta.error) {
    return <Alerta tono="neutro" titulo="No se pudo cargar la evidencia guardada" />;
  }
  return consulta.data ? <EvidenciaGuardada evidencia={consulta.data} /> : null;
}
