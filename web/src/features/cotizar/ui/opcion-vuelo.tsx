"use client";

import { useId, useState } from "react";
import { Distintivo } from "@/shared/ui/distintivo";
import { clasesBoton } from "@/shared/ui/boton";
import { Alerta } from "@/shared/ui/estado";
import { formatearDinero } from "@/shared/ui/formato";
import { GIRO, PRESIONAR } from "@/shared/ui/movimiento";
import {
  ORIGEN_LINEA,
  diasDespues,
  duracion,
  hora,
  segmentosCosto,
  textoOrigenDato,
  type AnalisisVuelo,
  type OpcionesBuscador,
  type OpcionVuelo,
  type SegmentoCosto,
  type TablaVendedor,
  tablasPorVendedor,
} from "../domain/cotizar";
import { useAnalisisVuelo, useOpcionesBuscador, useRegistrarFuente } from "../application/cotizar";

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
      {/* El cuerpo parte en cualquier punto (overflow-wrap: anywhere): en la tabla los importes y el origen no se parten */}
      <table className="w-full text-sm [overflow-wrap:normal]">
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
              <td className="whitespace-nowrap py-1.5 pr-2 text-texto-secundario">{ORIGEN_LINEA[l.origen] ?? l.origen}</td>
              <td className="whitespace-nowrap py-1.5 text-right tabular-nums">{formatearDinero(l.valor_usd)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-texto">
            <th scope="row" colSpan={2} className="py-1.5 text-left">
              Costo total esperado
            </th>
            <td className="whitespace-nowrap py-1.5 text-right font-bold tabular-nums">{formatearDinero(vuelo.costo_total_usd)}</td>
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
  cotizacionId,
}: {
  vuelo: OpcionVuelo;
  maximo: number;
  elegible: boolean;
  elegido: boolean;
  onElegir: () => void;
  nombreGrupo: string;
  cotizacionId: number;
}) {
  const [abierto, setAbierto] = useState(false);
  const registrarFuente = useRegistrarFuente(cotizacionId);
  const analisis = useAnalisisVuelo(cotizacionId, vuelo.id);
  const buscador = useOpcionesBuscador(cotizacionId, vuelo.id, abierto);
  // Abrir el desglose abre también la página oficial del vendedor (el mismo enlace, en otra pestaña; el servidor deja
  // el rastro del clic) y pide leer la página del vuelo en Google Flights. El servidor reutiliza una lectura de menos
  // de una hora: volver a abrir no gasta otra.
  function abrirDesglose() {
    setAbierto(true);
    if (!analisis.isPending) analisis.mutate();
  }
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
      {vuelo.total_con_hotel_usd ? (
        <p className="text-sm text-texto-secundario">
          Total con el hotel recomendado:{" "}
          <span className="whitespace-nowrap font-semibold text-texto tabular-nums">{formatearDinero(vuelo.total_con_hotel_usd)}</span>
        </p>
      ) : null}
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
        {abierto ? (
          <button
            type="button"
            aria-expanded
            aria-controls={desglose}
            onClick={() => setAbierto(false)}
            className={`-ml-1 inline-flex min-h-11 items-center gap-1 px-1 font-semibold text-marca underline underline-offset-3 hover:text-marca-oscura ${PRESIONAR}`}
          >
            <span aria-hidden="true" className={`${GIRO} rotate-90`}>
              ›
            </span>
            Ocultar desglose
          </button>
        ) : (
          <a
            href={vuelo.vendedor_url}
            target="_blank"
            rel="noopener noreferrer"
            aria-expanded={false}
            aria-controls={desglose}
            aria-label="Ver desglose (abre también la página oficial del vendedor en otra pestaña)"
            onClick={abrirDesglose}
            onAuxClick={(e) => {
              if (e.button === 1) abrirDesglose();
            }}
            className={`-ml-1 inline-flex min-h-11 items-center gap-1 px-1 font-semibold text-marca underline underline-offset-3 hover:text-marca-oscura ${PRESIONAR}`}
          >
            <span aria-hidden="true" className={GIRO}>
              ›
            </span>
            Ver desglose
            <span aria-hidden="true">↗</span>
          </a>
        )}
        {vuelo.fuente_url ? (
        <a
          href={vuelo.fuente_url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Ver en Google Flights (${nombreVuelo(vuelo)}), se abre en otra pestaña`}
          onClick={() => registrarFuente("vuelos", { vueloId: vuelo.id })}
          onAuxClick={(e) => {
            if (e.button === 1) registrarFuente("vuelos", { vueloId: vuelo.id });
          }}
          className={`ml-3 inline-flex min-h-11 items-center gap-1 px-1 text-sm text-texto-secundario underline underline-offset-3 hover:text-texto ${PRESIONAR}`}
        >
          Ver en Google Flights
          <span aria-hidden="true">↗</span>
        </a>
        ) : null}
        <div id={desglose} className={abierto ? "mt-2 flex flex-col gap-4" : ""}>
          {abierto ? (
            <>
              <Desglose vuelo={vuelo} />
              <CapaBuscador esperando={buscador.esperando} error={Boolean(buscador.error)} opciones={buscador.data} />
              <DetalleGoogle
                pendiente={analisis.isPending}
                agotado={analisis.agotado}
                error={analisis.error ? "No hubo conexión con el servidor." : null}
                analisis={analisis.data ?? null}
              />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** «HH:MM» en la hora local de quien mira. */
function horaLocal(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit", hour12: false });
}

const COLUMNAS: readonly { clave: "mano" | "maleta" | "cambios" | "reembolso" | "asiento"; titulo: string }[] = [
  { clave: "mano", titulo: "Maleta de mano" },
  { clave: "maleta", titulo: "Primera maleta" },
  { clave: "cambios", titulo: "Cambios" },
  { clave: "reembolso", titulo: "Reembolso" },
  { clave: "asiento", titulo: "Asiento" },
];

/**
 * Una tabla por vendedor y una fila por tarifa, con su «Ir a…». En el celular cada fila se apila con el nombre de
 * cada columna delante: nada se desplaza de lado.
 */
function TablaDeVendedor({ tabla }: { tabla: TablaVendedor }) {
  const celda = "flex gap-2 py-1 md:table-cell md:py-1.5 md:pr-3 md:align-top before:shrink-0 before:font-semibold " +
    "before:text-texto-secundario before:content-[attr(data-titulo)] md:before:content-none";
  return (
    <table className="w-full text-sm [overflow-wrap:anywhere]">
      <caption className="mb-1 text-left font-semibold">
        {tabla.vendedor} <span className="font-normal text-texto-secundario">(según {tabla.filas[0]?.origen === "buscador" ? "el buscador" : "la página"})</span>
      </caption>
      <thead className="sr-only md:not-sr-only">
        <tr className="text-left text-texto-secundario">
          <th scope="col" className="py-1 pr-3 font-semibold">Tarifa</th>
          <th scope="col" className="py-1 pr-3 text-right font-semibold">Precio</th>
          {COLUMNAS.map((c) => (
            <th key={c.clave} scope="col" className="py-1 pr-3 font-semibold">{c.titulo}</th>
          ))}
          <th scope="col" className="py-1 pr-3 font-semibold">Origen</th>
          <th scope="col" className="py-1 font-semibold"><span className="sr-only">Comprar</span></th>
        </tr>
      </thead>
      <tbody>
        {tabla.filas.map((f) => (
          <tr key={`${f.tarifa}-${f.precio}`} className="block border-t border-linea py-2 md:table-row md:py-0">
            <th scope="row" data-titulo="Tarifa:" className={`${celda} text-left font-semibold`}>{f.tarifa}</th>
            <td data-titulo="Precio:" className={`${celda} tabular-nums md:text-right md:whitespace-nowrap`}>
              {formatearDinero(f.precio.toFixed(2))}
            </td>
            {COLUMNAS.map((c) => (
              <td key={c.clave} data-titulo={`${c.titulo}:`} className={celda}>{f[c.clave]}</td>
            ))}
            <td data-titulo="Origen:" className={celda}>{f.origen}</td>
            <td className="py-1 md:table-cell md:py-1.5">
              {f.ir_url ? (
              <a
                href={f.ir_url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Ir a ${f.vendedor}, ${f.tarifa}, se abre en otra pestaña`}
                className={`inline-flex min-h-11 items-center gap-1 whitespace-nowrap px-1 font-semibold text-marca underline underline-offset-3 hover:text-marca-oscura ${PRESIONAR}`}
              >
                Ir a {f.vendedor}
                <span aria-hidden="true">↗</span>
              </a>
              ) : null}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Primera capa: lo que trajo el buscador, en 2 a 5 s; no espera a la lectura de la página. */
function CapaBuscador({
  esperando,
  error,
  opciones,
}: {
  esperando: boolean;
  error: boolean;
  opciones: OpcionesBuscador | null;
}) {
  const listo = opciones?.estado === "listo" && opciones.tarifas.length > 0;
  return (
    <section aria-label="Opciones del buscador" className="flex flex-col gap-3 border-t border-linea pt-3">
      <p role="status" className={`text-sm ${listo ? "font-semibold" : "text-texto-secundario"}`}>
        {listo
          ? `Opciones de reserva del buscador${opciones.consultado ? ` (consultadas a las ${horaLocal(opciones.consultado)})` : ""}`
          : esperando
            ? "Buscando las opciones de reserva…"
            : error
              ? "No se pudieron traer las opciones del buscador."
              : "El buscador no trajo opciones de reserva para este vuelo."}
      </p>
      {listo
        ? tablasPorVendedor(opciones.tarifas, "buscador").map((t) => <TablaDeVendedor key={t.vendedor} tabla={t} />)
        : null}
    </section>
  );
}

/**
 * Lo esencial de la página del vuelo en Google Flights: un botón por tarifa de la aerolínea, que lleva a su página (el
 * servidor deja guardado todo lo leído, con su captura, como evidencia). Si el precio de la página no es el del
 * buscador, lo dice; la comparación sigue con el del buscador.
 */
function DetalleGoogle({
  pendiente,
  agotado = false,
  error,
  analisis,
}: {
  pendiente: boolean;
  /** Se siguió una lectura en curso hasta el límite y no terminó. */
  agotado?: boolean;
  error: string | null;
  analisis: AnalisisVuelo | null;
}) {
  if (agotado) {
    return (
      <section aria-label="Ir a la aerolínea" className="flex flex-col gap-3 border-t border-linea pt-3">
        <p role="status" className="text-sm text-texto-secundario">
          La lectura sigue en curso; vuelve a abrir el desglose en un momento.
        </p>
      </section>
    );
  }
  const lectura = pendiente || analisis?.estado === "pendiente";
  const tarifas = !lectura && analisis?.estado === "listo" && analisis.datos ? tarifasDeLaAerolinea(analisis.datos) : [];
  return (
    <section aria-label="Ir a la aerolínea" className="flex flex-col gap-3 border-t border-linea pt-3">
      <p role="status" className={`text-sm ${lectura || analisis?.estado !== "listo" ? "text-texto-secundario" : "font-semibold"}`}>
        {lectura
          ? "Leyendo la página del vuelo…"
          : error
            ? `No se pudo leer la página: ${error}`
            : !analisis
              ? ""
              : analisis.estado === "listo"
                ? analisis.datos?.tarifas.length
                  ? `Tarifas de la aerolínea leídas a las ${horaLocal(analisis.leido)}`
                  : "La página no mostró tarifas de la aerolínea: puedes verla en Google Flights."
                : analisis.estado === "fallido"
                  ? `No se pudo leer la página: ${analisis.motivo ?? "sin motivo"}.`
                  : analisis.motivo}
      </p>
      {!lectura && analisis?.aviso_precio ? (
        <Alerta tono="aviso" titulo="El precio de la página no es el del buscador">
          <p>{analisis.aviso_precio}</p>
        </Alerta>
      ) : null}
      {tarifas.length ? (
        <ul className="flex flex-wrap gap-2">
          {tarifas.map((t) => (
            <li key={`${t.vendedor}-${t.nombre}-${t.precio}`}>
              <a
                href={t.ir_url!}
                target="_blank"
                rel="noopener noreferrer"
                className={`${clasesBoton("secundario")} ${PRESIONAR}`}
              >
                Ir a {t.vendedor} · {t.nombre}
                <span className="font-normal tabular-nums"> {formatearDinero(t.precio.toFixed(2))}</span>
                <span aria-hidden="true"> ↗</span>
                <span className="sr-only">, se abre en otra pestaña</span>
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Las tarifas con «Ir a…» de la aerolínea; si la página no muestra la aerolínea como vendedor, las que haya. */
function tarifasDeLaAerolinea(d: NonNullable<AnalisisVuelo["datos"]>) {
  const aerolineas = new Set(d.vendedores.filter((v) => v.aerolinea).map((v) => v.vendedor));
  const conEnlace = d.tarifas.filter((t) => t.ir_url);
  const propias = conEnlace.filter((t) => aerolineas.has(t.vendedor));
  return propias.length ? propias : conEnlace;
}
