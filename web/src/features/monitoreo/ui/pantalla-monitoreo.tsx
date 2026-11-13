"use client";

import Link from "next/link";
import { consultaDeDireccion, filtrosEnDireccion, formatearValor, type FiltrosTablero as Filtros } from "@/features/kpis/domain/kpis";
import { FiltrosTablero } from "@/features/kpis/ui/filtros-tablero";
import { clasesBoton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoIndicadores, EsqueletoLista } from "@/shared/ui/esqueleto";
import { Indicador, Indicadores } from "@/shared/ui/indicador";
import { useMonitoreoRepository, usePestanaMonitoreo } from "../application/monitoreo";
import { PESTANAS, esEnlace, maximoDeBarras, type Celda, type Columna, type Pestana, type PestanaMonitoreo, type TablaMonitoreo } from "../domain/monitoreo";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

const TITULOS: Record<Pestana, string> = {
  viajes: "Viajes",
  gastos: "Gastos",
  busquedas: "Búsquedas",
  modelo: "Modelo de lenguaje",
  cupos: "Cupos",
  auditoria: "Auditoría",
  calidad: "Calidad",
};

function textoCelda(celda: Celda, columna: Columna | undefined): string {
  if (celda === null || celda === "") return "—";
  if (typeof celda === "number") return columna?.unidad ? formatearValor(celda, columna.unidad) : formatearValor(celda, "").trim();
  return esEnlace(celda) ? celda.texto : celda;
}

function ContenidoCelda({ celda, columna }: { celda: Celda; columna: Columna | undefined }) {
  if (esEnlace(celda)) {
    return (
      <Link href={celda.href} className="whitespace-nowrap font-semibold">
        {celda.texto}
      </Link>
    );
  }
  return <>{textoCelda(celda, columna)}</>;
}

/** Barra proporcional al mayor valor de la tabla; la cifra siempre va escrita al lado. */
function Barra({ valor, maximo }: { valor: Celda; maximo: number }) {
  const ancho = typeof valor === "number" && maximo > 0 ? Math.max(2, Math.round((valor / maximo) * 100)) : 0;
  return (
    <span aria-hidden="true" className="block h-2 w-full rounded-full bg-neutro-suave">
      <span className="block h-2 rounded-full bg-marca" style={{ width: `${ancho}%` }} />
    </span>
  );
}

function TablaPestana({ tabla }: { tabla: TablaMonitoreo }) {
  const maximo = tabla.barras ? maximoDeBarras(tabla) : 0;
  return (
    <section aria-label={tabla.titulo} className={`${TARJETA} min-w-0`}>
      <h2 className="text-lg font-bold">{tabla.titulo}</h2>
      {tabla.nota ? <p className="mt-1 text-sm text-texto-secundario">{tabla.nota}</p> : null}
      {tabla.filas.length === 0 ? (
        <p className="mt-2 text-texto-secundario">{tabla.vacio}</p>
      ) : (
        <div className="mt-2 overflow-x-auto" tabIndex={0} role="region" aria-label={`${tabla.titulo} (se desliza de lado)`}>
          <table className="w-full text-left">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-texto-secundario">
                {tabla.columnas.map((c) => (
                  <th key={c.texto} scope="col" className={`whitespace-nowrap py-2 pr-3 ${c.fin ? "text-right" : ""}`}>
                    {c.texto}
                  </th>
                ))}
                {tabla.barras ? (
                  <th scope="col" className="w-1/3 py-2">
                    <span className="sr-only">Proporción</span>
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {tabla.filas.map((fila, i) => (
                <tr key={i} className="border-t border-linea">
                  {fila.map((celda, j) => (
                    <td
                      key={j}
                      className={`py-2 pr-3 align-top ${tabla.columnas[j]?.fin ? "whitespace-nowrap text-right tabular-nums" : "break-words"}`}
                    >
                      <ContenidoCelda celda={celda} columna={tabla.columnas[j]} />
                    </td>
                  ))}
                  {tabla.barras ? (
                    <td className="py-2 align-middle">
                      <Barra valor={fila[1] ?? null} maximo={maximo} />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Pestanas({ actual, filtros }: { actual: Pestana; filtros: Filtros }) {
  return (
    <nav aria-label="Pestañas de Monitoreo">
      <ul className="flex flex-wrap gap-2">
        {PESTANAS.map((p) => (
          <li key={p}>
            <Link
              href={`/monitoreo${consultaDeDireccion({ pestana: p, ...filtrosEnDireccion(filtros) })}`}
              aria-current={p === actual ? "page" : undefined}
              className={`inline-flex min-h-11 items-center rounded-full border px-4 font-semibold no-underline ${
                p === actual ? "border-marca bg-marca text-sobre-marca" : "border-borde-campo bg-superficie text-texto hover:bg-neutro-suave"
              }`}
            >
              {TITULOS[p]}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Exportar({ p, filtros }: { p: PestanaMonitoreo; filtros: Filtros }) {
  const repositorio = useMonitoreoRepository();
  if (p.exportar.length === 0) return null;
  const enlaces = p.exportar.map((e) => ({ ...e, url: repositorio.urlExportar(e.vista, filtros) }));
  return (
    <section aria-labelledby="titulo-exportar" className={`${TARJETA} flex flex-col gap-2`}>
      <h2 id="titulo-exportar" className="text-lg font-bold">
        Descargar en CSV
      </h2>
      {enlaces.every((e) => e.url === null) ? (
        <p className="text-texto-secundario">La descarga está disponible con la plataforma conectada.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {enlaces.map((e) =>
            e.url ? (
              <a key={e.vista} href={e.url} className={clasesBoton("secundario")}>
                {e.texto}
              </a>
            ) : null,
          )}
        </div>
      )}
    </section>
  );
}

function Contenido({ p, filtros }: { p: PestanaMonitoreo; filtros: Filtros }) {
  return (
    <>
      {p.cifras.length ? (
        <Indicadores etiqueta={`Cifras de ${p.titulo}`}>
          {p.cifras.map((c) => (
            <Indicador
              key={c.etiqueta}
              etiqueta={c.etiqueta}
              cifra={typeof c.valor === "number" ? formatearValor(c.valor, c.unidad ?? "").trim() : (c.valor ?? "Sin datos")}
              pie={c.pie}
            />
          ))}
        </Indicadores>
      ) : null}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {p.tablas.map((t) => (
          <div key={t.titulo} className={t.columnas.length > 3 ? "min-w-0 lg:col-span-2" : "min-w-0"}>
            <TablaPestana tabla={t} />
          </div>
        ))}
      </div>
      <Exportar p={p} filtros={filtros} />
    </>
  );
}

export function PantallaMonitoreo({ pestana, filtros }: { pestana: Pestana; filtros: Filtros }) {
  const consulta = usePestanaMonitoreo(pestana, filtros);
  const p = consulta.data;
  return (
    <div className="flex min-w-0 flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Administración" }, { texto: "Monitoreo", href: "/monitoreo" }, { texto: TITULOS[pestana] }]}
        titulo="Monitoreo"
        descripcion={
          p?.nota ??
          "Cada cifra sale del catálogo de métricas, con una sola definición, y se calcula sobre los hechos registrados."
        }
      />
      {p ? <FiltrosTablero ruta="/monitoreo" filtros={filtros} proyectos={p.proyectos} extra={{ pestana }} /> : null}
      <Pestanas actual={pestana} filtros={filtros} />
      {p ? (
        <Contenido p={p} filtros={filtros} />
      ) : consulta.error ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} volverA={{ href: "/resumen", texto: "Ir al resumen" }} />
      ) : (
        <>
          <EsqueletoIndicadores />
          <EsqueletoLista texto="Cargando el monitoreo…" />
        </>
      )}
    </div>
  );
}
