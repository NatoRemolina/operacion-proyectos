"use client";

import Link from "next/link";
import { estadoVisibleGasto } from "@/features/gastos/domain/gastos";
import { clasesBoton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoIndicadores, EsqueletoLista } from "@/shared/ui/esqueleto";
import { InsigniaEstado } from "@/shared/ui/estado";
import { EstadoVacio } from "@/shared/ui/estado-vacio";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearDinero, formatearRango } from "@/shared/ui/formato";
import { Indicador, Indicadores } from "@/shared/ui/indicador";
import { Tabla } from "@/shared/ui/tabla";
import { useResumen } from "../application/administracion";
import type { ActividadGasto, ResumenAdmin } from "../domain/administracion";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";

function plural(n: number, uno: string, varios: string) {
  return `${n} ${n === 1 ? uno : varios}`;
}

function ViajesPorAprobar({ resumen }: { resumen: ResumenAdmin }) {
  return (
    <section aria-labelledby="titulo-por-aprobar" className={`${TARJETA} md:col-span-3`}>
      <div className="flex items-center justify-between gap-3">
        <h2 id="titulo-por-aprobar" className="text-lg font-bold">
          Viajes por aprobar
        </h2>
        <span className="text-sm text-texto-secundario">{plural(resumen.viajes_por_aprobar, "viaje", "viajes")}</span>
      </div>
      {resumen.pendientes.length === 0 ? (
        <p className="mt-2 text-texto-secundario">No hay viajes esperando aprobación.</p>
      ) : (
        <ul className="mt-2 flex flex-col">
          {resumen.pendientes.map((v) => (
            <li key={v.id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 border-b border-linea py-3 last:border-b-0">
              <div className="min-w-0">
                <Link href={`/viajes/${v.id}`} className="font-semibold">
                  {v.codigo} · {v.titular?.nombre ?? "Sin titular"}
                </Link>
                <p className="text-sm text-texto-secundario">
                  {v.origen} → {v.destino} · {formatearRango(v.ida, v.regreso)}
                </p>
                {v.precio_por_confirmar ? (
                  <p className="mt-1">
                    <InsigniaEstado tono="aviso">Precio por confirmar</InsigniaEstado>
                  </p>
                ) : null}
                {v.propio ? <p className="mt-1 text-sm text-texto-secundario">Es tuyo: lo aprueba otra persona.</p> : null}
              </div>
              <p className="font-semibold tabular-nums">{formatearDinero(v.presupuesto_usd, "USD")}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function GastosEnRevision({ resumen }: { resumen: ResumenAdmin }) {
  return (
    <section aria-labelledby="titulo-en-revision" className={`${TARJETA} md:col-span-2`}>
      <div className="flex items-center justify-between gap-3">
        <h2 id="titulo-en-revision" className="text-lg font-bold">
          Gastos en revisión
        </h2>
        <span className="text-sm text-texto-secundario">{plural(resumen.gastos_en_revision, "gasto", "gastos")}</span>
      </div>
      {resumen.revision.length === 0 ? (
        <p className="mt-2 text-texto-secundario">No hay gastos esperando revisión.</p>
      ) : (
        <>
          <ul className="mt-2 flex flex-col">
            {resumen.revision.map((g) => (
              <li key={g.id} className="flex items-center justify-between gap-4 border-b border-linea py-3 last:border-b-0">
                <Link href={`/gastos/${g.id}`} className="min-w-0 font-semibold">
                  {g.comercio ?? "Gasto sin comercio leído"}
                </Link>
                <span className="whitespace-nowrap tabular-nums">{formatearDinero(g.total, g.moneda)}</span>
              </li>
            ))}
          </ul>
          <Link href="/gastos?estado=revision" className="mt-2 inline-flex min-h-11 items-center">
            Ver todos los gastos en revisión
          </Link>
        </>
      )}
    </section>
  );
}

function ActividadReciente({ resumen }: { resumen: ResumenAdmin }) {
  return (
    <section aria-labelledby="titulo-actividad" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 id="titulo-actividad" className="text-lg font-bold">
          Actividad reciente
        </h2>
        {resumen.datos_demostracion ? (
          <span className="text-sm text-texto-secundario">Solo datos de demostración</span>
        ) : null}
      </div>
      {resumen.actividad.length === 0 ? (
        <EstadoVacio titulo="Todavía no hay gastos">
          Cuando alguien cargue un recibo, aparecerá aquí con su estado.
        </EstadoVacio>
      ) : (
        <Tabla<ActividadGasto>
          titulo="Actividad reciente"
          filas={resumen.actividad}
          claveFila={(a) => a.gasto_id}
          hrefFila={(a) => `/gastos/${a.gasto_id}`}
          columnas={[
            { clave: "comercio", encabezado: "Comercio", celda: (a) => a.comercio ?? "Sin comercio leído", principal: true },
            { clave: "persona", encabezado: "Persona", celda: (a) => a.persona?.nombre ?? "Sin asignar" },
            { clave: "viaje", encabezado: "Viaje", celda: (a) => a.viaje?.codigo ?? "Sin viaje", sinCorte: true },
            {
              clave: "importe",
              encabezado: "Importe",
              // En la columna «Importe» basta «Por confirmar», más corto y en gris: la cifra que falta no compite.
              celda: (a) =>
                a.total === null ? (
                  <span className="text-texto-secundario">Por confirmar</span>
                ) : (
                  formatearDinero(a.total, a.moneda)
                ),
              alinear: "fin",
            },
            {
              clave: "estado",
              encabezado: "Estado",
              celda: (a) => <EtiquetaEstado estado={estadoVisibleGasto(a.estado)} texto={a.estado_texto} />,
            },
          ]}
          acciones={(a) => {
            const revisar = a.estado === "revision";
            const nombre = a.comercio ?? "sin comercio leído";
            return (
              <Link
                href={`/gastos/${a.gasto_id}`}
                aria-label={revisar ? `Revisar el gasto de ${nombre}` : `Ver detalle del gasto de ${nombre}`}
                className="inline-flex min-h-11 items-center font-semibold"
              >
                {revisar ? "Revisar" : "Ver detalle"}
              </Link>
            );
          }}
        />
      )}
    </section>
  );
}

function Contenido({ resumen }: { resumen: ResumenAdmin }) {
  return (
    <>
      <Indicadores etiqueta="Indicadores del presupuesto">
        <Indicador
          etiqueta="Presupuesto aprobado"
          cifra={formatearDinero(resumen.presupuesto_aprobado_usd, "USD")}
          pie="En viajes aprobados y cerrados"
        />
        <Indicador
          etiqueta="Gastado"
          cifra={formatearDinero(resumen.gastado_usd, "USD")}
          pie={resumen.ejecucion_pct === null ? "Sin presupuesto aprobado" : `${resumen.ejecucion_pct} % del aprobado`}
        />
        <Indicador etiqueta="Disponible" cifra={formatearDinero(resumen.disponible_usd, "USD")} pie="Aprobado menos gastado" />
        <Indicador
          etiqueta="En revisión"
          cifra={formatearDinero(resumen.en_revision_usd, "USD")}
          pie={plural(resumen.gastos_en_revision, "gasto por revisar", "gastos por revisar")}
          destacado={resumen.gastos_en_revision > 0}
        />
      </Indicadores>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
        <ViajesPorAprobar resumen={resumen} />
        <GastosEnRevision resumen={resumen} />
      </div>
      <ActividadReciente resumen={resumen} />
      <p className="text-sm text-texto-secundario">{resumen.nota}</p>
    </>
  );
}

export function PantallaResumen() {
  const consulta = useResumen();
  const resumen = consulta.data;
  const accion = resumen ? (
    resumen.viajes_por_aprobar > 0 ? (
      <Link href="/viajes?estado=pendiente_aprobacion" className={clasesBoton("primario")}>
        Aprobar viajes
      </Link>
    ) : resumen.gastos_en_revision > 0 ? (
      <Link href="/gastos?estado=revision" className={clasesBoton("primario")}>
        Revisar gastos
      </Link>
    ) : null
  ) : null;

  return (
    <div className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Operaciones" }, { texto: "Resumen" }]}
        titulo="Resumen"
        descripcion="Cómo va el presupuesto de los viajes y qué espera tu decisión."
        accion={accion}
      />
      {resumen ? (
        <Contenido resumen={resumen} />
      ) : consulta.error ? (
        <ErrorConsulta
          error={consulta.error}
          onReintentar={() => void consulta.refetch()}
          volverA={{ href: "/viajes", texto: "Ir a mis viajes" }}
        />
      ) : (
        <>
          <EsqueletoIndicadores />
          <EsqueletoLista texto="Cargando el resumen…" />
        </>
      )}
    </div>
  );
}
