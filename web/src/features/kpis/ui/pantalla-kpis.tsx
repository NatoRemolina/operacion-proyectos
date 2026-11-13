"use client";

import Link from "next/link";
import { clasesBoton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoIndicadores, EsqueletoLista } from "@/shared/ui/esqueleto";
import { InsigniaEstado } from "@/shared/ui/estado";
import { Tabla } from "@/shared/ui/tabla";
import { useKpisRepository, useTableroKpis } from "../application/kpis";
import { formatearValor, type ExportableKpis, type FilaPersona, type FiltrosTablero as Filtros, type TableroKpis } from "../domain/kpis";
import { FiltrosTablero } from "./filtros-tablero";
import { SemaforoKpi, TablaPares, TablaSimple, TarjetaKpi, TARJETA, pct, usd } from "./piezas";

const EXPORTAR: readonly { que: ExportableKpis; texto: string }[] = [
  { que: "kpis", texto: "Indicadores" },
  { que: "consultas", texto: "Consultas al buscador" },
  { que: "personas", texto: "Personas" },
];

function Resumen({ t }: { t: TableroKpis }) {
  return (
    <ul aria-label="Cuántos indicadores hay en cada estado" className="flex flex-wrap gap-2">
      <li>
        <SemaforoKpi estado="verde">{t.resumen.verde} en meta</SemaforoKpi>
      </li>
      <li>
        <SemaforoKpi estado="ambar">{t.resumen.ambar} en atención</SemaforoKpi>
      </li>
      <li>
        <SemaforoKpi estado="rojo">{t.resumen.rojo} fuera de meta</SemaforoKpi>
      </li>
      <li>
        <SemaforoKpi estado="sin datos">{t.resumen.sin_datos} sin datos</SemaforoKpi>
      </li>
    </ul>
  );
}

function Tendencia({ t, hasta }: { t: TableroKpis; hasta: string | null }) {
  const { semanas, filas } = t.tendencia;
  return (
    <TablaSimple
      titulo="Tendencia semanal"
      nota={`Indicadores principales, semana a semana (de lunes a domingo), hasta ${hasta ?? "hoy"}. Cada semana se calcula sobre los hechos de esa semana.`}
      encabezados={[{ texto: "Indicador" }, ...semanas.map((s) => ({ texto: s.slice(5), fin: true }))]}
      filas={filas.map((f) => ({
        clave: f.nombre,
        celdas: [
          f.titulo,
          ...f.puntos.map((p, i) =>
            p.valor === null ? (
              <span key={i} className="text-texto-secundario">
                —
              </span>
            ) : (
              <SemaforoKpi key={i} estado={p.estado}>
                {formatearValor(p.valor, f.unidad)}
              </SemaforoKpi>
            ),
          ),
        ],
      }))}
      vacio="Sin indicadores principales."
    />
  );
}

function Cotizacion({ t }: { t: TableroKpis }) {
  const c = t.cotizacion;
  return (
    <section aria-labelledby="titulo-det-cotizacion" className="flex flex-col gap-4">
      <h2 id="titulo-det-cotizacion" className="text-xl font-bold">
        Detalle de la cotización
      </h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <TablaPares titulo="Consultas al buscador por origen" pares={c.consultas_por_origen} columnas={["Origen", "Consultas"]} />
        <TablaPares titulo="Consultas al buscador por tipo" pares={c.consultas_por_tipo} columnas={["Tipo", "Consultas"]} />
        <TablaPares titulo="Cotizaciones por persona" pares={c.cotizaciones_por_persona} columnas={["Persona", "Cotizaciones"]} />
        <TablaPares titulo="Cotizaciones por ruta" pares={c.cotizaciones_por_ruta} columnas={["Ruta", "Cotizaciones"]} />
        <TablaPares titulo="Quién usa el buscador" pares={c.consultas_por_persona} columnas={["Persona", "Consultas"]} />
        <TablaSimple
          titulo="Fallas recientes del buscador"
          encabezados={[{ texto: "Momento" }, { texto: "Tipo" }, { texto: "Error" }]}
          filas={c.errores_buscador.map((e, i) => ({ clave: i, celdas: [e.momento ?? "—", e.tipo ?? "—", e.error ?? "—"] }))}
          vacio="Ninguna falla en el periodo."
          nota={
            c.cupo
              ? `Cupo del plan: ${c.cupo.usadas ?? "?"} de ${c.cupo.mensual ?? "?"} búsquedas usadas este mes (${c.cupo.restantes ?? "?"} restantes).`
              : "Sin clave del buscador configurada: el cupo no se puede consultar."
          }
        />
      </div>
    </section>
  );
}

function Gastos({ t }: { t: TableroKpis }) {
  const g = t.gastos;
  const grupo = (titulo: string, filas: TableroKpis["gastos"]["por_proyecto"], nota?: string) => (
    <TablaSimple
      titulo={titulo}
      nota={nota}
      encabezados={[{ texto: "Nombre" }, { texto: "Presupuesto", fin: true }, { texto: "Aprobado", fin: true }, { texto: "Ejecución", fin: true }]}
      filas={filas.map((x, i) => ({ clave: `${x.nombre}-${i}`, celdas: [x.nombre ?? "—", usd(x.presupuesto), usd(x.gastado), pct(x.pct)] }))}
      vacio="Sin viajes con presupuesto aprobado."
    />
  );
  return (
    <section aria-labelledby="titulo-det-gastos" className="flex flex-col gap-4">
      <h2 id="titulo-det-gastos" className="text-xl font-bold">
        Detalle de gastos
      </h2>
      <TablaSimple
        titulo="Ejecución del presupuesto por viaje"
        encabezados={[
          { texto: "Viaje" },
          { texto: "Titular" },
          { texto: "Ruta" },
          { texto: "Ida" },
          { texto: "Estado" },
          { texto: "Presupuesto", fin: true },
          { texto: "Aprobado", fin: true },
          { texto: "En revisión", fin: true },
          { texto: "Ejecución", fin: true },
        ]}
        filas={g.por_viaje.map((v) => ({
          clave: v.id,
          celdas: [
            <Link key="v" href={`/viajes/${v.id}`} className="whitespace-nowrap font-semibold">
              {v.codigo}
            </Link>,
            v.titular ?? "—",
            v.ruta ?? "—",
            v.ida ?? "—",
            v.estado,
            usd(v.presupuesto),
            usd(v.gastado),
            usd(v.en_revision),
            pct(v.pct),
          ],
        }))}
        vacio="Sin viajes en el periodo."
      />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {grupo("Ejecución por proyecto", g.por_proyecto)}
        {grupo(
          "Ejecución por categoría",
          g.por_categoria,
          "El presupuesto se arma por grupo de compra; comida, combustible, peajes y otros salen de los viáticos.",
        )}
        <TablaSimple
          titulo="Gasto aprobado por moneda"
          encabezados={[{ texto: "Moneda" }, { texto: "Gastos", fin: true }, { texto: "Total", fin: true }, { texto: "En USD", fin: true }]}
          filas={g.por_moneda.map((m, i) => ({
            clave: `${m.moneda}-${i}`,
            celdas: [m.moneda ?? "—", m.gastos, m.total === null ? "—" : `${m.moneda ?? ""} ${m.total.toFixed(2)}`, usd(m.total_usd)],
          }))}
          vacio="Sin gastos aprobados en el periodo."
        />
        <TablaSimple
          titulo="Gastos que más llevan en revisión"
          encabezados={[{ texto: "Gasto" }, { texto: "Persona" }, { texto: "USD", fin: true }, { texto: "Días", fin: true }]}
          filas={g.revision_antiguas.map((x) => ({
            clave: x.id,
            celdas: [
              <Link key="g" href={`/gastos/${x.id}`}>
                #{x.id} {x.comercio ?? ""}
              </Link>,
              x.persona ?? "—",
              usd(x.total_usd),
              x.dias ?? "—",
            ],
          }))}
          vacio="Ningún gasto espera revisión."
        />
      </div>
      <TablaSimple
        titulo="Gasto por cargo"
        nota="El cargo de un viaje es el de su titular; el de un gasto, el del titular de su viaje o, sin viaje, el de quien lo cargó."
        encabezados={[{ texto: "Cargo" }, { texto: "Viajes", fin: true }, { texto: "Gasto aprobado", fin: true }, { texto: "En revisión", fin: true }]}
        filas={t.por_cargo.map((c) => ({ clave: c.cargo, celdas: [c.cargo, c.viajes, usd(c.gasto_usd), usd(c.en_revision)] }))}
        vacio="Sin viajes ni gastos en el periodo."
      />
    </section>
  );
}

function Personas({ t }: { t: TableroKpis }) {
  return (
    <section aria-labelledby="titulo-personas" className="flex flex-col gap-3">
      <h2 id="titulo-personas" className="text-xl font-bold">
        Personas
      </h2>
      <p className="text-sm text-texto-secundario">
        A cada persona le pertenece lo que la tiene como titular (quien viaja); un gasto sin viaje, a quien lo cargó. Abre la
        ficha para ver todo lo suyo por su ID.
      </p>
      <Tabla<FilaPersona>
        titulo="Personas"
        filas={t.personas}
        claveFila={(p) => p.id}
        hrefFila={(p) => `/kpis/persona/${p.id}`}
        columnas={[
          {
            clave: "nombre",
            encabezado: "Persona",
            principal: true,
            celda: (p) => (
              <>
                <span className="tabular-nums">{p.codigo}</span> · {p.nombre}
                {p.activo ? null : (
                  <>
                    {" "}
                    <InsigniaEstado tono="neutro">Inactiva</InsigniaEstado>
                  </>
                )}
              </>
            ),
          },
          { clave: "rol", encabezado: "Rol", celda: (p) => p.rol_texto },
          { clave: "cotizaciones", encabezado: "Cotizaciones", celda: (p) => p.cotizaciones, alinear: "fin" },
          { clave: "viajes", encabezado: "Viajes", celda: (p) => p.viajes, alinear: "fin" },
          { clave: "presupuesto", encabezado: "Presupuesto", celda: (p) => usd(p.presupuesto), alinear: "fin" },
          { clave: "gastado", encabezado: "Gasto aprobado", celda: (p) => usd(p.gastado), alinear: "fin" },
          { clave: "ejecucion", encabezado: "Ejecución", celda: (p) => pct(p.ejecucion), alinear: "fin" },
          { clave: "revision", encabezado: "En revisión", celda: (p) => p.gastos_revision, alinear: "fin" },
        ]}
      />
    </section>
  );
}

function Exportar({ filtros }: { filtros: Filtros }) {
  const repositorio = useKpisRepository();
  const enlaces = EXPORTAR.map((e) => ({ ...e, url: repositorio.urlExportar(e.que, filtros) }));
  return (
    <section aria-labelledby="titulo-exportar" className={`${TARJETA} flex flex-col gap-2`}>
      <h2 id="titulo-exportar" className="text-lg font-bold">
        Descargar en CSV
      </h2>
      <p className="text-sm text-texto-secundario">Con los mismos filtros de la pantalla.</p>
      {enlaces.every((e) => e.url === null) ? (
        <p className="text-texto-secundario">La descarga está disponible con la plataforma conectada; en el modo de demostración no hay datos que exportar.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {enlaces.map((e) =>
            e.url ? (
              // Un enlace y no una petición: el navegador lo descarga con la sesión y el nombre que da el servidor.
              <a key={e.que} href={e.url} className={clasesBoton("secundario")}>
                {e.texto}
              </a>
            ) : null,
          )}
        </div>
      )}
    </section>
  );
}

function Contenido({ t, filtros }: { t: TableroKpis; filtros: Filtros }) {
  return (
    <>
      <Resumen t={t} />
      {t.retos.map((r) => (
        <section key={r.reto} aria-labelledby={`titulo-reto-${r.reto}`} className="flex flex-col gap-3">
          <h2 id={`titulo-reto-${r.reto}`} className="text-xl font-bold">
            Reto {r.reto}: {r.nombre}
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {t.kpis
              .filter((k) => k.reto === r.reto)
              .map((k) => (
                <TarjetaKpi key={k.nombre} kpi={k} />
              ))}
          </div>
        </section>
      ))}
      <Tendencia t={t} hasta={filtros.hasta} />
      <Cotizacion t={t} />
      <Gastos t={t} />
      <Personas t={t} />
      <Exportar filtros={filtros} />
    </>
  );
}

export function PantallaKpis({ filtros }: { filtros: Filtros }) {
  const consulta = useTableroKpis(filtros);
  const t = consulta.data;
  return (
    <div className="flex min-w-0 flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Administración" }, { texto: "KPIs" }]}
        titulo="Indicadores (KPIs)"
        descripcion="Cada indicador tiene una meta, un umbral de alerta y un responsable. Sin datos no hay color: el indicador dice «sin datos». Las metas son supuestos editables en Reglas y supuestos (ámbito «kpi»)."
      />
      {t ? <FiltrosTablero ruta="/kpis" filtros={filtros} proyectos={t.proyectos} /> : null}
      {t ? (
        <Contenido t={t} filtros={filtros} />
      ) : consulta.error ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} volverA={{ href: "/resumen", texto: "Ir al resumen" }} />
      ) : (
        <>
          <EsqueletoIndicadores />
          <EsqueletoLista texto="Cargando los indicadores…" />
        </>
      )}
    </div>
  );
}
