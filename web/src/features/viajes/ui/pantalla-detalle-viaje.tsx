"use client";

import Link from "next/link";
import { AccionesViaje } from "@/features/administracion/ui/acciones-viaje";
import { DecisionViaje } from "@/features/administracion/ui/decision-viaje";
import { useGastos } from "@/features/gastos/application/gastos";
import { estadoVisibleGasto } from "@/features/gastos/domain/gastos";
import { clasesBoton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle } from "@/shared/ui/esqueleto";
import { Alerta } from "@/shared/ui/estado";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { formatearDinero, formatearRango } from "@/shared/ui/formato";
import { Tabla } from "@/shared/ui/tabla";
import { useViaje } from "../application/viajes";
import { estadoVisibleViaje, type LineaPresupuesto, type ViajeDetalle } from "../domain/viajes";
import { BarraPresupuesto } from "./barra-presupuesto";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-sm";

/** Qué sigue según el estado: cada viaje dice cuál es el próximo paso y de quién es. */
function SiguientePaso({ viaje }: { viaje: ViajeDetalle }) {
  if (viaje.estado === "pendiente_aprobacion") return <DecisionViaje viaje={viaje} />;
  if (viaje.estado === "rechazado") {
    return (
      <div className="flex flex-col gap-3">
        <Alerta tono="error" titulo="Presupuesto rechazado">
          <p>{viaje.motivo ?? "Administración no dejó el motivo."}</p>
        </Alerta>
        {viaje.propio ? (
          <p>
            <Link href="/cotizar" className={clasesBoton("primario")}>
              Cotizar de nuevo
            </Link>
          </p>
        ) : null}
        <AccionesViaje viaje={viaje} />
      </div>
    );
  }
  if (viaje.estado === "cerrado") {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-texto-secundario">Viaje cerrado: ya no recibe gastos.</p>
        <AccionesViaje viaje={viaje} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-texto-secundario">
        {viaje.en_curso ? "El viaje está en curso." : "Presupuesto aprobado."} Los recibos se cargan a este viaje.
      </p>
      <AccionesViaje viaje={viaje} />
    </div>
  );
}

function Desglose({ viaje }: { viaje: ViajeDetalle }) {
  return (
    <section aria-labelledby="titulo-presupuesto" className={`${TARJETA} flex flex-col gap-4`}>
      <h2 id="titulo-presupuesto" className="text-lg font-bold">
        Presupuesto
      </h2>
      <BarraPresupuesto
        presupuesto={viaje.presupuesto_usd}
        gastado={viaje.gastado_usd}
        enRevision={viaje.en_revision_usd}
        porcentaje={viaje.ejecucion_pct}
      />
      {viaje.presupuesto_detalle.length ? (
        <>
          <Tabla<LineaPresupuesto & { orden: number }>
            titulo="Desglose del presupuesto"
            filas={viaje.presupuesto_detalle.map((l, orden) => ({ ...l, orden }))}
            claveFila={(l) => l.orden}
            columnas={[
              { clave: "concepto", encabezado: "Concepto", celda: (l) => l.concepto, principal: true },
              { clave: "valor", encabezado: "Importe", celda: (l) => formatearDinero(l.valor, "USD"), alinear: "fin" },
            ]}
          />
          <p className="flex justify-between border-t border-linea pt-3 font-bold">
            <span>Total del presupuesto</span>
            <span className="tabular-nums">{formatearDinero(viaje.presupuesto_usd, "USD")}</span>
          </p>
        </>
      ) : (
        <p className="text-texto-secundario">Este viaje no tiene desglose guardado.</p>
      )}
    </section>
  );
}

function GastosDelViaje({ viaje }: { viaje: ViajeDetalle }) {
  const consulta = useGastos({ viajeId: viaje.id });
  return (
    <section aria-labelledby="titulo-gastos-viaje" className={`${TARJETA} flex flex-col gap-3`}>
      <h2 id="titulo-gastos-viaje" className="text-lg font-bold">
        Gastos del viaje
      </h2>
      {consulta.isPending ? (
        <p role="status" className="text-texto-secundario">
          Cargando los gastos…
        </p>
      ) : consulta.error ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : consulta.gastos.length === 0 ? (
        <p className="text-texto-secundario">Todavía no hay gastos en este viaje.</p>
      ) : (
        <ul aria-label="Gastos del viaje" className="flex flex-col">
          {consulta.gastos.map((g) => (
            <li key={g.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-linea py-3 last:border-b-0">
              <div className="flex flex-wrap items-center gap-2">
                <Link href={`/gastos/${g.id}`} className="font-semibold">
                  {g.comercio ?? "Gasto sin comercio leído"}
                </Link>
                <EtiquetaEstado estado={estadoVisibleGasto(g.estado)} texto={g.estado_texto} />
              </div>
              <span className="whitespace-nowrap tabular-nums">{formatearDinero(g.total, g.moneda)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PantallaDetalleViaje({ id }: { id: number }) {
  const consulta = useViaje(id);
  const viaje = consulta.data;
  const migas = [{ texto: "Viajes", href: "/viajes" }, { texto: viaje?.codigo ?? "Detalle del viaje" }];

  if (!viaje) {
    return (
      <div className="flex flex-col gap-6">
        <EncabezadoPagina migas={migas} titulo="Detalle del viaje" />
        {consulta.error ? (
          <ErrorConsulta
            error={consulta.error}
            onReintentar={() => void consulta.refetch()}
            volverA={{ href: "/viajes", texto: "Volver a viajes" }}
          />
        ) : (
          <EsqueletoDetalle texto="Cargando el viaje…" />
        )}
      </div>
    );
  }

  const puedeCargar = viaje.estado === "aprobado" && viaje.propio;
  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        migas={migas}
        titulo={viaje.codigo}
        descripcion={
          <>
            {viaje.origen} → {viaje.destino} · {formatearRango(viaje.ida, viaje.regreso)}
            {viaje.proyecto ? ` · ${viaje.proyecto.nombre}` : ""}
            {viaje.titular ? ` · ${viaje.titular.nombre} (${viaje.titular.codigo})` : ""}
          </>
        }
        accion={
          puedeCargar ? (
            <Link href={`/gastos/nuevo?viaje=${viaje.id}`} className={clasesBoton("primario")}>
              Cargar recibo
            </Link>
          ) : null
        }
      />
      <section aria-labelledby="titulo-estado" className={`${TARJETA} flex flex-col gap-3`}>
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="titulo-estado" className="text-lg font-bold">
            Estado
          </h2>
          <EtiquetaEstado estado={estadoVisibleViaje(viaje)} texto={viaje.en_curso ? "En curso" : viaje.estado_texto} />
        </div>
        <SiguientePaso viaje={viaje} />
      </section>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Desglose viaje={viaje} />
        <GastosDelViaje viaje={viaje} />
      </div>
    </div>
  );
}
