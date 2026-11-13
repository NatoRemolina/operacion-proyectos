"use client";

import Link from "next/link";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle } from "@/shared/ui/esqueleto";
import { InsigniaEstado } from "@/shared/ui/estado";
import { Indicador, Indicadores } from "@/shared/ui/indicador";
import { formatearInstante } from "@/shared/ui/formato";
import { useFichaPersona } from "../application/kpis";
import type { FichaPersona } from "../domain/kpis";
import { TablaPares, TablaSimple, TarjetaKpi, pct, usd } from "./piezas";

function LineaDeTiempo({ eventos }: { eventos: FichaPersona["eventos"] }) {
  return (
    <section aria-labelledby="titulo-linea" className="flex flex-col gap-3">
      <h2 id="titulo-linea" className="text-xl font-bold">
        Línea de tiempo
      </h2>
      <p className="text-sm text-texto-secundario">
        Los hechos sobre lo suyo, aunque los haya registrado otra persona (por ejemplo, la aprobación). Del más reciente al más
        antiguo.
      </p>
      {eventos.length === 0 ? (
        <p className="text-texto-secundario">Todavía no hay hechos registrados sobre esta persona.</p>
      ) : (
        <ol className="flex flex-col border-l-2 border-linea pl-4">
          {eventos.map((e, i) => (
            <li key={`${e.momento}-${i}`} className="relative py-2">
              <span aria-hidden="true" className="absolute top-4 -left-[1.4rem] size-2.5 rounded-full bg-marca" />
              <p className="text-sm text-texto-secundario">
                <time dateTime={e.momento}>{formatearInstante(e.momento)}</time>
                {e.quien ? ` · ${e.quien}` : ""}
                {e.fuente ? ` · ${e.fuente}` : ""}
              </p>
              <p>
                <span className="font-semibold">{e.paso}</span>
                {e.entidad ? (
                  <span className="text-texto-secundario">
                    {" "}
                    ({e.entidad}
                    {e.entidad_id ? ` #${e.entidad_id}` : ""})
                  </span>
                ) : null}
              </p>
              {e.detalle ? <p className="break-words text-sm">{e.detalle}</p> : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function Contenido({ p }: { p: FichaPersona }) {
  return (
    <>
      <Indicadores etiqueta="Totales de la persona">
        <Indicador etiqueta="Presupuesto aprobado" cifra={usd(p.totales.presupuesto)} pie="En viajes aprobados y cerrados" />
        <Indicador etiqueta="Gasto aprobado" cifra={usd(p.totales.gastado)} />
        <Indicador etiqueta="En revisión" cifra={usd(p.totales.en_revision)} />
        <Indicador etiqueta="Viajes" cifra={p.viajes.length} pie={`${p.cotizaciones.length} cotizaciones · ${p.gastos.length} gastos`} />
      </Indicadores>
      <section aria-labelledby="titulo-ind-persona" className="flex flex-col gap-3">
        <h2 id="titulo-ind-persona" className="text-xl font-bold">
          Sus indicadores
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {p.indicadores.map((k) => (
            <TarjetaKpi key={k.nombre} kpi={k} />
          ))}
        </div>
      </section>
      <TablaSimple
        titulo="Viajes"
        encabezados={[
          { texto: "Viaje" },
          { texto: "Ruta" },
          { texto: "Ida" },
          { texto: "Estado" },
          { texto: "Presupuesto", fin: true },
          { texto: "Aprobado", fin: true },
          { texto: "Ejecución", fin: true },
        ]}
        filas={p.viajes.map((v) => ({
          clave: v.id,
          celdas: [
            <Link key="v" href={`/viajes/${v.id}`} className="whitespace-nowrap font-semibold">
              {v.codigo}
            </Link>,
            `${v.origen ?? "—"} → ${v.destino ?? "—"}`,
            v.ida ?? "—",
            v.estado_texto,
            usd(v.presupuesto_usd),
            usd(v.gastado),
            pct(v.pct),
          ],
        }))}
        vacio="No tiene viajes."
      />
      <TablaSimple
        titulo="Cotizaciones"
        encabezados={[{ texto: "Cotización" }, { texto: "Ruta" }, { texto: "Ida" }, { texto: "Proyecto" }, { texto: "Viaje" }]}
        filas={p.cotizaciones.map((c) => ({
          clave: c.id,
          celdas: [
            <Link key="c" href={`/cotizar/${c.id}`}>
              #{c.id}
            </Link>,
            `${c.origen ?? "—"} → ${c.destino ?? "—"}`,
            c.ida ?? "—",
            c.proyecto ?? "—",
            c.viaje ?? "Sin decidir",
          ],
        }))}
        vacio="No tiene cotizaciones."
      />
      <TablaSimple
        titulo="Gastos"
        encabezados={[
          { texto: "Gasto" },
          { texto: "Fecha" },
          { texto: "Categoría" },
          { texto: "Viaje" },
          { texto: "Canal" },
          { texto: "Estado" },
          { texto: "Total", fin: true },
          { texto: "En USD", fin: true },
        ]}
        filas={p.gastos.map((g) => ({
          clave: g.id,
          celdas: [
            <Link key="g" href={`/gastos/${g.id}`}>
              #{g.id} {g.comercio ?? ""}
            </Link>,
            g.fecha ?? "—",
            g.categoria ?? "—",
            g.viaje ?? "Sin viaje",
            g.canal ?? "—",
            g.estado,
            g.total === null ? "—" : `${g.moneda ?? ""} ${g.total.toFixed(2)}`,
            usd(g.total_usd),
          ],
        }))}
        vacio="No tiene gastos."
      />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <TablaPares titulo="Gastos por estado" pares={p.gastos_por_estado} columnas={["Estado", "Gastos"]} vacio="Sin gastos." />
        <TablaPares titulo="Gastos por canal" pares={p.gastos_por_canal} columnas={["Canal", "Gastos"]} vacio="Sin gastos." />
      </div>
      <TablaSimple
        titulo="Evidencias"
        encabezados={[{ texto: "Archivo" }, { texto: "Tipo" }, { texto: "Canal" }, { texto: "Viaje" }, { texto: "Llegó" }]}
        filas={p.evidencias.map((d) => ({
          clave: d.id,
          celdas: [d.nombre ?? `#${d.id}`, d.tipo ?? "—", d.canal ?? "—", d.viaje ?? "Sin viaje", d.creado ?? "—"],
        }))}
        vacio="No tiene evidencias."
      />
      <LineaDeTiempo eventos={p.eventos} />
    </>
  );
}

export function PantallaFichaPersona({ id }: { id: number }) {
  const consulta = useFichaPersona(id);
  const p = consulta.data;
  return (
    <div className="flex min-w-0 flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Administración" }, { texto: "KPIs", href: "/kpis" }, { texto: p ? p.usuario.codigo : "Persona" }]}
        titulo={p ? `${p.usuario.codigo} · ${p.usuario.nombre}` : "Ficha de la persona"}
        descripcion={
          p ? (
            <span className="flex flex-wrap items-center gap-2">
              {p.usuario.rol_texto} · {p.usuario.cargo ?? "Sin cargo"} · {p.usuario.correo}
              {p.usuario.base ? ` · base ${p.usuario.base}` : ""}
              {p.usuario.activo ? null : <InsigniaEstado tono="neutro">Inactiva</InsigniaEstado>}
            </span>
          ) : (
            "Todo lo de una persona por su ID, y nada de otra."
          )
        }
      />
      {p ? (
        <Contenido p={p} />
      ) : consulta.error ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} volverA={{ href: "/kpis", texto: "Volver a los KPIs" }} />
      ) : (
        <EsqueletoDetalle texto="Cargando la ficha…" />
      )}
    </div>
  );
}
