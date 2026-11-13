"use client";

import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { Alerta, InsigniaEstado, type Tono } from "@/shared/ui/estado";
import { Tabla } from "@/shared/ui/tabla";
import { useRutasFrecuentes } from "../application/kpis";
import {
  TRAMOS_ANTICIPACION,
  formatearValor,
  textoTendencia,
  type RutaFrecuente,
  type RutasFrecuentes,
  type ValorSenal,
} from "../domain/kpis";
import { TablaSimple, TARJETA } from "./piezas";

const TONO_SENAL: Record<ValorSenal, Tono> = { "por debajo": "exito", dentro: "info", "por encima": "aviso", "sin datos": "neutro" };

/** Una cifra en USD; sin dato, una raya (la tabla no repite «Sin datos» en cada celda). */
function usdCorto(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "—" : formatearValor(valor, "USD");
}

function textoPrima(p: RutaFrecuente["prima_flexibilidad"]): string {
  if (!p || p.usd === null) return "—";
  return `${usdCorto(p.usd)}${p.pct === null ? "" : ` (${formatearValor(p.pct, "%")})`}`;
}

function textoAgencia(a: RutaFrecuente["aerolinea_agencia"]): string {
  if (!a || a.diferencia_usd === null) return "—";
  if (a.diferencia_usd === 0) return "igual";
  return a.diferencia_usd > 0
    ? `aerolínea ${usdCorto(a.diferencia_usd)} más barata`
    : `agencia ${usdCorto(-a.diferencia_usd)} más barata`;
}

function Senal({ r }: { r: RutaFrecuente }) {
  const s = r.senal;
  const etiqueta = s.valor === "sin datos" ? "Sin datos" : `${s.valor[0]!.toUpperCase()}${s.valor.slice(1)} del rango`;
  return (
    <span className="inline-flex flex-col gap-1">
      <InsigniaEstado tono={TONO_SENAL[s.valor]}>{etiqueta}</InsigniaEstado>
      {s.referencia && s.rango ? (
        <span className="text-xs text-texto-secundario">
          {usdCorto(s.precio)} frente a {usdCorto(s.rango[0])}–{usdCorto(s.rango[1])} ({s.referencia})
        </span>
      ) : null}
    </span>
  );
}

function Exactitud({ d }: { d: RutasFrecuentes }) {
  const e = d.exactitud;
  return (
    <TablaSimple
      titulo="Exactitud del precio esperado"
      nota={
        e.mensaje ??
        `Error medio ${usdCorto(e.mae)} (${formatearValor(e.mape, "%")}) en ${e.filas} vuelos mostrados al decidir, frente al precio del buscador en ese momento.${
          e.contra_pagado ? ` Frente a lo pagado: ${usdCorto(e.contra_pagado.mae)} (${formatearValor(e.contra_pagado.mape, "%")}).` : ""
        }`
      }
      encabezados={[{ texto: "Ruta" }, { texto: "Vuelos", fin: true }, { texto: "Error medio", fin: true }, { texto: "Error %", fin: true }]}
      filas={e.por_ruta.map((r) => ({
        clave: r.ruta,
        celdas: [r.ruta, r.filas, usdCorto(r.mae), r.mape === null ? "—" : formatearValor(r.mape, "%")],
      }))}
      vacio="Sin decisiones con precio esperado todavía."
    />
  );
}

function Contenido({ d }: { d: RutasFrecuentes }) {
  return (
    <>
      <Alerta tono={d.pocos_datos ? "aviso" : "info"} titulo={d.pocos_datos ? "Cifras demostrativas" : "Cómo leer estas cifras"}>
        <p>{d.aviso}</p>
        <p className="text-sm text-texto-secundario">
          {d.tarifas_vistas} tarifas vistas útiles tras la limpieza. Rutas ordenadas por cotizaciones y viajes de los últimos {d.dias} días.
        </p>
      </Alerta>
      {d.rutas.length === 0 ? (
        <p className={`${TARJETA} text-texto-secundario`}>Todavía no hay cotizaciones en los últimos {d.dias} días.</p>
      ) : (
        <Tabla<RutaFrecuente>
          titulo="Precios por ruta frecuente"
          tituloVisible
          filas={d.rutas}
          claveFila={(r) => r.ruta}
          columnas={[
            {
              clave: "ruta",
              encabezado: "Ruta",
              principal: true,
              sinCorte: true,
              celda: (r) => r.ruta,
            },
            { clave: "uso", encabezado: "Cotizaciones · viajes", celda: (r) => `${r.cotizaciones} · ${r.viajes}`, alinear: "fin" },
            ...TRAMOS_ANTICIPACION.map((t) => ({
              clave: `tramo-${t}`,
              encabezado: `${t} días`,
              celda: (r: RutaFrecuente) => usdCorto(r.por_anticipacion[t]),
              alinear: "fin" as const,
            })),
            { clave: "volatilidad", encabezado: "Variación típica", celda: (r) => usdCorto(r.volatilidad), alinear: "fin" },
            { clave: "prima", encabezado: "Prima de flexibilidad", celda: (r) => textoPrima(r.prima_flexibilidad), alinear: "fin" },
            { clave: "agencia", encabezado: "Aerolínea o agencia", celda: (r) => textoAgencia(r.aerolinea_agencia) },
            { clave: "tendencia", encabezado: "Tendencia", celda: (r) => textoTendencia(r.tendencia) },
            { clave: "senal", encabezado: "Último precio", celda: (r) => <Senal r={r} /> },
          ]}
        />
      )}
      <Exactitud d={d} />
    </>
  );
}

/** «Rutas frecuentes y precios»: lo que dicen los precios vistos de las rutas más usadas y cuánto acierta el modelo. */
export function SeccionRutasFrecuentes() {
  const consulta = useRutasFrecuentes();
  return (
    <section aria-labelledby="titulo-rutas-frecuentes" className="flex min-w-0 flex-col gap-4">
      <h2 id="titulo-rutas-frecuentes" className="text-xl font-bold">
        Rutas frecuentes y precios
      </h2>
      <p className="text-sm text-texto-secundario">
        Mediana del precio por días de anticipación, cuánto más cuesta una tarifa con cambio gratis o maleta incluida, si conviene
        comprar a la aerolínea o a una agencia, y si el último precio visto está dentro de lo habitual.
      </p>
      {consulta.data ? (
        <Contenido d={consulta.data} />
      ) : consulta.error ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : (
        <EsqueletoLista texto="Cargando las rutas frecuentes…" />
      )}
    </section>
  );
}
