"use client";

import Link from "next/link";
import { useState } from "react";
import { estadoVisibleGasto, problemaDePeriodo, type PeriodoContable } from "@/features/gastos/domain/gastos";
import { estadoVisibleViaje } from "@/features/viajes/domain/viajes";
import { usePermiso } from "@/shared/application/identidad";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { CampoTexto } from "@/shared/ui/campo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle } from "@/shared/ui/esqueleto";
import { Alerta } from "@/shared/ui/estado";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearDinero, formatearFecha, formatearRango } from "@/shared/ui/formato";
import { Indicador, Indicadores } from "@/shared/ui/indicador";
import { Tabla } from "@/shared/ui/tabla";
import {
  useEditarProyecto,
  useTableroProyecto,
  useUrlCsvProyecto,
  useUrlLibroContableProyecto,
} from "../application/proyectos";
import {
  datosDeProyecto,
  proporcion,
  type CategoriaProyecto,
  type GastoDelProyecto,
  type TableroProyecto,
} from "../domain/proyectos";
import { Diferencia } from "./diferencia";
import { FormularioProyecto } from "./formulario-proyecto";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

function Comparacion({ tablero }: { tablero: TableroProyecto }) {
  const maximo = Math.max(0, ...tablero.categorias.flatMap((c) => [Number(c.previsto_usd ?? 0), Number(c.real_usd ?? 0)]));
  return (
    <section aria-labelledby="titulo-comparacion" className={`${TARJETA} flex flex-col gap-4`}>
      <div>
        <h2 id="titulo-comparacion" className="text-lg font-bold">
          Previsto frente a real por categoría
        </h2>
        <p className="max-w-prose text-sm text-texto-secundario">
          El previsto es la suma de los presupuestos de los viajes del proyecto (lo que se compra más los viáticos por
          día): la misma cifra que aprueba administración. El real son los gastos aprobados.
        </p>
      </div>
      {tablero.categorias.length === 0 ? (
        <p className="text-texto-secundario">Aún no hay presupuesto previsto ni gastos aprobados en este proyecto.</p>
      ) : (
        <>
          {/* Las barras acompañan a la tabla: la misma información va escrita debajo. */}
          <ul aria-hidden="true" className="flex flex-col gap-3">
            {tablero.categorias.map((c) => (
              <li key={c.clave} className="flex flex-col gap-1">
                <span className="text-sm font-semibold">{c.nombre}</span>
                <span className="flex items-center gap-2">
                  <span className="h-2.5 rounded-full bg-marca-suave" style={{ width: `${proporcion(c.previsto_usd, maximo)}%` }} />
                  <span className="text-xs text-texto-secundario">Previsto</span>
                </span>
                <span className="flex items-center gap-2">
                  <span
                    className={`h-2.5 rounded-full ${Number(c.real_usd ?? 0) > Number(c.previsto_usd ?? 0) ? "bg-error" : "bg-marca"}`}
                    style={{ width: `${proporcion(c.real_usd, maximo)}%` }}
                  />
                  <span className="text-xs text-texto-secundario">Real</span>
                </span>
              </li>
            ))}
          </ul>
          <Tabla<CategoriaProyecto>
            titulo="Previsto frente a real por categoría"
            filas={tablero.categorias}
            claveFila={(c) => c.clave}
            columnas={[
              { clave: "nombre", encabezado: "Categoría", celda: (c) => c.nombre, principal: true },
              { clave: "previsto", encabezado: "Previsto", celda: (c) => formatearDinero(c.previsto_usd, "USD"), alinear: "fin" },
              { clave: "real", encabezado: "Real", celda: (c) => formatearDinero(c.real_usd, "USD"), alinear: "fin" },
              { clave: "diferencia", encabezado: "Diferencia", celda: (c) => <Diferencia valor={c.diferencia_usd} compacta />, alinear: "fin" },
            ]}
          />
        </>
      )}
    </section>
  );
}

function Descargas({ tablero }: { tablero: TableroProyecto }) {
  const id = tablero.proyecto.id;
  const [periodo, setPeriodo] = useState<PeriodoContable>(tablero.periodo_contable);
  const urlExcel = useUrlLibroContableProyecto(id, periodo);
  const hayPlataforma = useUrlCsvProyecto(id) !== null;
  const problema = problemaDePeriodo(periodo);
  return (
    <section aria-labelledby="titulo-excel-proyecto" className={`${TARJETA} flex flex-col gap-4`}>
      <div>
        <h2 id="titulo-excel-proyecto" className="text-lg font-bold">
          Excel contable del proyecto
        </h2>
        <p className="max-w-prose text-sm text-texto-secundario">
          Los gastos aprobados de este proyecto en el periodo, por la fecha del recibo, con su cuenta contable.
        </p>
      </div>
      <div className="grid gap-3 sm:max-w-md sm:grid-cols-2">
        <CampoTexto
          id="proyecto-contable-desde"
          etiqueta="Desde"
          type="date"
          required
          value={periodo.desde}
          onChange={(e) => setPeriodo((p) => ({ ...p, desde: e.target.value }))}
        />
        <CampoTexto
          id="proyecto-contable-hasta"
          etiqueta="Hasta"
          type="date"
          required
          value={periodo.hasta}
          error={problema}
          onChange={(e) => setPeriodo((p) => ({ ...p, hasta: e.target.value }))}
        />
      </div>
      {urlExcel ? (
        // Un enlace y no una petición: el navegador lo descarga con la sesión y el nombre que da el servidor.
        <a href={urlExcel} className={clasesBoton("primario", "self-start")}>
          Descargar Excel contable
        </a>
      ) : (
        <div className="flex flex-col items-start gap-2">
          <Boton disabled>Descargar Excel contable</Boton>
          {!problema && !hayPlataforma ? (
            <p className="text-sm text-texto-secundario">
              La descarga está disponible con la plataforma conectada; en el modo de demostración no hay libro contable.
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}

function ViajesDelProyecto({ tablero }: { tablero: TableroProyecto }) {
  return (
    <section aria-labelledby="titulo-viajes-proyecto" className={`${TARJETA} flex flex-col gap-3`}>
      <h2 id="titulo-viajes-proyecto" className="text-lg font-bold">
        Viajes del proyecto
      </h2>
      {tablero.viajes.length === 0 ? (
        <p className="text-texto-secundario">
          Este proyecto aún no tiene viajes, así que no hay presupuesto previsto.{" "}
          <Link href="/cotizar">Cotizar un viaje</Link>
        </p>
      ) : (
        <ul aria-label="Viajes del proyecto" className="flex flex-col">
          {tablero.viajes.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-linea py-3 last:border-b-0">
              <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                <Link href={`/viajes/${v.id}`} className="font-semibold whitespace-nowrap">
                  {v.codigo}
                </Link>
                <span className="text-sm text-texto-secundario">{v.titular?.nombre ?? "Sin titular"}</span>
                <EtiquetaEstado estado={estadoVisibleViaje(v)} texto={v.estado_texto} />
              </span>
              <span className="whitespace-nowrap text-sm tabular-nums">{formatearDinero(v.presupuesto_usd, "USD")}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function GastosDelProyecto({ tablero }: { tablero: TableroProyecto }) {
  return (
    <section aria-labelledby="titulo-gastos-proyecto" className="flex flex-col gap-3">
      <h2 id="titulo-gastos-proyecto" className="text-xl font-bold">
        Gastos del proyecto
      </h2>
      {tablero.gastos.length === 0 ? (
        <p className={`${TARJETA} text-texto-secundario`}>Sin gastos todavía.</p>
      ) : (
        <Tabla<GastoDelProyecto>
          titulo="Gastos del proyecto"
          filas={tablero.gastos}
          claveFila={(g) => g.id}
          hrefFila={(g) => `/gastos/${g.id}`}
          columnas={[
            { clave: "comercio", encabezado: "Comercio", celda: (g) => g.comercio ?? "Gasto sin comercio leído", principal: true },
            { clave: "fecha", encabezado: "Fecha", celda: (g) => formatearFecha(g.fecha), sinCorte: true },
            { clave: "viajero", encabezado: "Viajero", celda: (g) => g.viajero ?? "—" },
            { clave: "estado", encabezado: "Estado", celda: (g) => <EtiquetaEstado estado={estadoVisibleGasto(g.estado)} texto={g.estado_texto} /> },
            { clave: "total", encabezado: "Total", celda: (g) => formatearDinero(g.total, g.moneda), alinear: "fin" },
            { clave: "usd", encabezado: "USD", celda: (g) => formatearDinero(g.total_usd, "USD"), alinear: "fin" },
          ]}
        />
      )}
    </section>
  );
}

export function PantallaTableroProyecto({ id }: { id: number }) {
  const consulta = useTableroProyecto(id);
  const esAdmin = usePermiso() === "admin";
  const editar = useEditarProyecto(id);
  const urlCsv = useUrlCsvProyecto(id);
  const { avisar } = useAvisos();
  const [editando, setEditando] = useState(false);
  const tablero = consulta.data;
  const migas = [{ texto: "Proyectos", href: "/proyectos" }, { texto: tablero?.proyecto.nombre ?? "Tablero del proyecto" }];

  if (!tablero) {
    return (
      <div className="flex flex-col gap-6 md:gap-8">
        <EncabezadoPagina migas={migas} titulo="Tablero del proyecto" />
        {consulta.error ? (
          <ErrorConsulta
            error={consulta.error}
            onReintentar={() => void consulta.refetch()}
            volverA={{ href: "/proyectos", texto: "Volver a proyectos" }}
          />
        ) : (
          <EsqueletoDetalle texto="Cargando el proyecto…" />
        )}
      </div>
    );
  }

  const p = tablero.proyecto;
  const datos = [p.cliente, p.ciudad, formatearRango(p.fecha_inicio, p.fecha_fin), `moneda ${p.moneda}`].filter(Boolean).join(" · ");
  return (
    <div className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={migas}
        titulo={p.nombre}
        descripcion={datos}
        accion={
          <>
            {urlCsv ? (
              <a href={urlCsv} className={clasesBoton("secundario")}>
                Exportar CSV
              </a>
            ) : (
              <Boton variante="secundario" disabled title="Disponible con la plataforma conectada">
                Exportar CSV
              </Boton>
            )}
            {esAdmin && !editando ? (
              <Boton
                onClick={() => {
                  editar.reset();
                  setEditando(true);
                }}
              >
                Editar proyecto
              </Boton>
            ) : null}
          </>
        }
      />

      {editando ? (
        <FormularioProyecto
          titulo="Editar proyecto"
          inicial={datosDeProyecto(p)}
          textoEnviar="Guardar cambios"
          guardando={editar.isPending}
          error={editar.error}
          onCancelar={() => setEditando(false)}
          onEnviar={(nuevos) =>
            editar.mutate(nuevos, {
              onSuccess: () => {
                setEditando(false);
                avisar({ tono: "exito", texto: "Proyecto actualizado." });
              },
            })
          }
        />
      ) : null}

      <Indicadores etiqueta="Cifras del proyecto">
        <Indicador etiqueta="Previsto" cifra={formatearDinero(tablero.previsto_usd, "USD")} pie="Presupuesto de los viajes" />
        <Indicador etiqueta="Real aprobado" cifra={formatearDinero(tablero.real_usd, "USD")} pie="Gastos aprobados" />
        <Indicador etiqueta="Diferencia" cifra={<Diferencia valor={tablero.diferencia_usd} alinear="inicio" />} pie="Real menos previsto" />
        <Indicador
          etiqueta="En revisión"
          cifra={tablero.en_revision}
          pie={tablero.en_revision === 1 ? "gasto espera revisión" : "gastos esperan revisión"}
          destacado={tablero.en_revision > 0}
        />
      </Indicadores>

      {tablero.faltantes.length ? (
        <Alerta tono="aviso" titulo="Soportes faltantes">
          <p>Hay gasto previsto pero no ha llegado soporte de {tablero.faltantes.join(", ")}.</p>
        </Alerta>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Comparacion tablero={tablero} />
        <div className="flex flex-col gap-6">
          <ViajesDelProyecto tablero={tablero} />
          <Descargas tablero={tablero} />
        </div>
      </div>

      <GastosDelProyecto tablero={tablero} />
    </div>
  );
}
