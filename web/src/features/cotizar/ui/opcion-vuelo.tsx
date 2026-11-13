"use client";

import { useId, useState } from "react";
import { Distintivo } from "@/shared/ui/distintivo";
import { formatearDinero } from "@/shared/ui/formato";
import { GIRO, PRESIONAR } from "@/shared/ui/movimiento";
import {
  ORIGEN_LINEA,
  diasDespues,
  duracion,
  hora,
  segmentosCosto,
  textoOrigenDato,
  type OpcionVuelo,
  type SegmentoCosto,
} from "../domain/cotizar";

const COLOR: Record<SegmentoCosto["tipo"], string> = {
  precio: "bg-marca",
  equipaje: "bg-cian-claro",
  riesgo_cambio: "bg-aviso",
  traslado: "bg-neutro",
};

export const LEYENDA: readonly { tipo: SegmentoCosto["tipo"]; nombre: string }[] = [
  { tipo: "precio", nombre: "Precio" },
  { tipo: "equipaje", nombre: "Equipaje" },
  { tipo: "riesgo_cambio", nombre: "Riesgo de cambio" },
  { tipo: "traslado", nombre: "Traslado" },
];

export function Leyenda() {
  return (
    <ul aria-label="Partes del costo en la barra" className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-texto-secundario">
      {LEYENDA.map((l) => (
        <li key={l.tipo} className="flex items-center gap-2">
          <span aria-hidden="true" className={`inline-block size-3 rounded-sm ${COLOR[l.tipo]}`} />
          {l.nombre}
        </li>
      ))}
      <li>Las millas restan y se ven en el desglose.</li>
    </ul>
  );
}

/** Barra del costo total esperado por partes; mide contra el vuelo más caro de la lista. Es apoyo visual: las cifras están en texto. */
export function BarraCosto({ vuelo, maximo }: { vuelo: OpcionVuelo; maximo: number }) {
  const partes = segmentosCosto(vuelo.desglose);
  return (
    <div aria-hidden="true" className="flex h-3 w-full overflow-hidden rounded-full bg-neutro-suave">
      {partes.map((p) => (
        <span
          key={p.tipo}
          className={`h-full border-r-2 border-superficie last:border-r-0 ${COLOR[p.tipo]}`}
          style={{ width: `${maximo > 0 ? (p.peso / maximo) * 100 : 0}%` }}
        />
      ))}
    </div>
  );
}

export function pesoTotal(vuelo: OpcionVuelo): number {
  return segmentosCosto(vuelo.desglose).reduce((suma, p) => suma + p.peso, 0);
}

export function nombreVuelo(v: Pick<OpcionVuelo, "aerolinea" | "numeros">): string {
  return `${v.aerolinea} ${v.numeros.join(" + ")}`;
}

export function Horario({ vuelo }: { vuelo: OpcionVuelo }) {
  const dias = diasDespues(vuelo.sale, vuelo.llega);
  return (
    <span className="tabular-nums">
      <b>{vuelo.desde}</b> {hora(vuelo.sale)} → <b>{vuelo.hasta}</b> {hora(vuelo.llega)}
      {dias > 0 ? <span className="text-texto-secundario"> (+{dias})</span> : null}
    </span>
  );
}

function Desglose({ vuelo }: { vuelo: OpcionVuelo }) {
  return (
    <div className="flex flex-col gap-2">
      <table className="w-full text-sm">
        <caption className="sr-only">Desglose del costo total esperado de {nombreVuelo(vuelo)}</caption>
        <thead>
          <tr className="text-left text-texto-secundario">
            <th scope="col" className="py-1 font-semibold">Concepto</th>
            <th scope="col" className="py-1 font-semibold">De dónde sale</th>
            <th scope="col" className="py-1 text-right font-semibold">Valor</th>
          </tr>
        </thead>
        <tbody>
          {vuelo.lineas.map((l) => (
            <tr key={l.concepto} className="border-t border-linea">
              <td className="py-1.5 pr-2">{l.concepto}</td>
              <td className="py-1.5 pr-2 text-texto-secundario">{ORIGEN_LINEA[l.origen] ?? l.origen}</td>
              <td className="py-1.5 text-right tabular-nums">{formatearDinero(l.valor_usd)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-texto">
            <th scope="row" colSpan={2} className="py-1.5 text-left">
              Costo total esperado
            </th>
            <td className="py-1.5 text-right font-bold tabular-nums">{formatearDinero(vuelo.costo_total_usd)}</td>
          </tr>
        </tfoot>
      </table>
      <p className="text-sm text-texto-secundario">
        Buscador: precio real de la búsqueda. Regla: valor del catálogo de la aerolínea. Supuesto: estimación editable
        (riesgo de cambio, millas, traslado).
        {vuelo.esperado_usd && vuelo.frente_esperado_pct !== null
          ? ` Según el modelo de precios, este vuelo está ${Math.abs(vuelo.frente_esperado_pct)} % ${
              vuelo.frente_esperado_pct >= 0 ? "por encima" : "por debajo"
            } de lo esperado para la ruta.`
          : ""}
      </p>
    </div>
  );
}

/**
 * Un vuelo de la comparación: lo que importa a la vista (horario, precio del buscador y costo total esperado)
 * y el desglose un nivel más abajo.
 */
export function OpcionDeVuelo({
  vuelo,
  maximo,
  elegible,
  elegido,
  onElegir,
  nombreGrupo,
}: {
  vuelo: OpcionVuelo;
  maximo: number;
  elegible: boolean;
  elegido: boolean;
  onElegir: () => void;
  nombreGrupo: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const titulo = useId();
  const desglose = useId();
  const origen = textoOrigenDato(vuelo.origen_dato);
  // Con el botón de elegir a la izquierda, lo que va debajo se alinea con el texto, no con el borde (size-5 + gap-3).
  const sangria = elegible ? "pl-8" : "";
  const cuerpo = (
    <>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 flex-col gap-1">
          <p id={titulo} className="font-bold">
            {nombreVuelo(vuelo)}
          </p>
          <p className="text-sm">
            <Horario vuelo={vuelo} />
            <span className="text-texto-secundario">
              {" "}· {vuelo.escalas === 0 ? "Directo" : vuelo.escalas === 1 ? "1 escala" : `${vuelo.escalas} escalas`}
              {vuelo.duracion_min !== null ? ` · ${duracion(vuelo.duracion_min)}` : ""}
            </span>
          </p>
          <p className="flex flex-wrap gap-1.5">
            {vuelo.recomendada ? <Distintivo tono="exito">Recomendada</Distintivo> : null}
            {vuelo.mas_barata ? <Distintivo tono="marca">La más barata</Distintivo> : null}
            <Distintivo tono={vuelo.tarifa.reales ? "exito" : "aviso"}>
              {vuelo.tarifa.reales ? "Tarifas reales" : "Tarifa supuesta"}
            </Distintivo>
            <Distintivo>{origen.texto}</Distintivo>
          </p>
        </div>
        <dl className="grid w-full grid-cols-2 gap-x-6 text-right sm:w-auto sm:min-w-64">
          <dt className="text-sm text-texto-secundario">Precio del buscador</dt>
          <dt className="text-sm text-texto-secundario">Costo total esperado</dt>
          <dd className="tabular-nums">{formatearDinero(vuelo.precio_usd)}</dd>
          <dd className="text-xl font-extrabold tracking-tight tabular-nums">{formatearDinero(vuelo.costo_total_usd)}</dd>
        </dl>
      </div>
      <BarraCosto vuelo={vuelo} maximo={maximo} />
    </>
  );
  return (
    <div
      role="group"
      aria-labelledby={titulo}
      // El elegido se marca con un anillo además del borde: el grosor no cambia y la tarjeta no salta al elegirla.
      className={`flex flex-col gap-3 rounded-tarjeta border bg-superficie p-4 transition-[box-shadow] duration-150 ease-salida ${
        elegido ? "border-marca ring-1 ring-marca" : vuelo.recomendada ? "border-exito" : "border-linea"
      }`}
    >
      {elegible ? (
        <label className="flex cursor-pointer gap-3">
          <input
            type="radio"
            name={nombreGrupo}
            className="mt-1 size-5 shrink-0 accent-marca"
            checked={elegido}
            onChange={onElegir}
            aria-label={`${nombreVuelo(vuelo)}, costo total esperado ${formatearDinero(vuelo.costo_total_usd)}`}
          />
          <span className="flex min-w-0 flex-1 flex-col gap-3">{cuerpo}</span>
        </label>
      ) : (
        cuerpo
      )}
      {vuelo.descartada ? (
        <p className={`text-sm font-semibold text-error ${sangria}`}>
          <span aria-hidden="true">✕ </span>
          <span>Descartado: </span>
          <span>{vuelo.descartada}</span>
        </p>
      ) : null}
      {vuelo.avisos.length ? (
        // Las advertencias se leen en el color del texto; el símbolo de aviso marca cada una sin teñir el párrafo
        // entero, y la sangría francesa alinea las líneas que se parten.
        <ul className={`flex flex-col gap-1 text-sm text-texto-secundario ${sangria}`}>
          {vuelo.avisos.map((a) => (
            <li key={a} className="grid grid-cols-[1rem_minmax(0,1fr)]">
              <span aria-hidden="true" className="font-bold text-aviso">
                !
              </span>
              <span>{a}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <div className={sangria}>
        <button
          type="button"
          aria-expanded={abierto}
          aria-controls={desglose}
          onClick={() => setAbierto((a) => !a)}
          className={`-ml-1 inline-flex min-h-11 items-center gap-1 px-1 font-semibold text-marca underline underline-offset-3 hover:text-marca-oscura ${PRESIONAR}`}
        >
          <span aria-hidden="true" className={`${GIRO} ${abierto ? "rotate-90" : ""}`}>
            ›
          </span>
          {abierto ? "Ocultar desglose" : "Ver desglose"}
        </button>
        <div id={desglose} className={abierto ? "mt-2" : ""}>
          {abierto ? <Desglose vuelo={vuelo} /> : null}
        </div>
      </div>
    </div>
  );
}
