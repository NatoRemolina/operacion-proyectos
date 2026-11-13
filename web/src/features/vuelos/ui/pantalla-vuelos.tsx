"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { CampoTexto } from "@/shared/ui/campo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { InsigniaEstado } from "@/shared/ui/estado";
import { EstadoVacio } from "@/shared/ui/estado-vacio";
import { Tabla } from "@/shared/ui/tabla";
import { useActualizarVuelo, useVuelosDelDia } from "../application/vuelos";
import { hora, textoActualizado, textoAviso, tonoDeVuelo, type TramoVuelo } from "../domain/vuelos";

function ElegirDia({ fecha }: { fecha: string | null }) {
  const router = useRouter();
  const [dia, setDia] = useState(fecha ?? "");
  function ver(e: FormEvent) {
    e.preventDefault();
    router.push(dia ? `/vuelos?fecha=${dia}` : "/vuelos");
  }
  return (
    <form onSubmit={ver} aria-label="Elegir el día" className="flex flex-wrap items-end gap-3">
      <div className="w-full sm:w-56">
        <CampoTexto id="vuelos-dia" etiqueta="Día" type="date" value={dia} onChange={(e) => setDia(e.target.value)} />
      </div>
      <Boton type="submit" variante="secundario">
        Ver
      </Boton>
      {fecha ? (
        <Link href="/vuelos" className="inline-flex min-h-11 items-center">
          Volver a hoy
        </Link>
      ) : null}
    </form>
  );
}

function Estado({ t }: { t: TramoVuelo }) {
  const aviso = textoAviso(t.aviso);
  return (
    <span className="flex flex-col items-start gap-1">
      <span className="flex flex-wrap gap-1">
        <InsigniaEstado tono={tonoDeVuelo(t.estado)}>
          {t.estado_texto}
          {t.retraso ? ` · ${t.retraso} min` : ""}
        </InsigniaEstado>
        {t.no_llega ? <InsigniaEstado tono="error">No llega a la grabación</InsigniaEstado> : null}
      </span>
      <span className="text-sm">
        Terminal {t.terminal ?? "—"} · puerta {t.puerta ?? "—"}
      </span>
      {t.no_llega && t.en_destino ? (
        <span className="text-sm text-texto-secundario">
          En destino {hora(t.en_destino)} con el traslado; hora límite {hora(t.llegar_antes)}.
        </span>
      ) : null}
      {aviso ? <span className="text-sm text-texto-secundario">{aviso}</span> : null}
    </span>
  );
}

function RutaYHoras({ t }: { t: TramoVuelo }) {
  const llegaCambio = t.llega_estimada && t.llega_estimada !== t.llega_programada;
  return (
    <span className="flex flex-col whitespace-nowrap">
      <span className="font-semibold">
        {t.desde ?? "?"} → {t.hasta ?? "?"}
      </span>
      <span className="text-sm">Sale {hora(t.sale_programada)}</span>
      <span className="text-sm">
        Llega {hora(t.llega_estimada ?? t.llega_programada)}
        {llegaCambio ? <span className="text-texto-secundario"> (prog. {hora(t.llega_programada)})</span> : null}
      </span>
    </span>
  );
}

/** De dónde salió el estado y cuándo se consultó; si la consulta automática está en pausa, por qué. */
function Consulta({ t }: { t: TramoVuelo }) {
  return (
    <span className="flex flex-col items-start gap-1 text-sm">
      {t.origen_texto ? (
        <InsigniaEstado tono={t.origen === "en vivo" ? "info" : "aviso"}>{t.origen_texto}</InsigniaEstado>
      ) : (
        <span className="text-texto-secundario">Sin datos aún</span>
      )}
      <span>{textoActualizado(t)}</span>
      {t.ultima_consulta === "sin datos" && t.estado !== "sin datos" ? (
        <span className="text-texto-secundario">La última consulta no trajo datos.</span>
      ) : null}
      {t.omitida ? <span className="text-texto-secundario">Consulta automática en pausa: {t.omitida}.</span> : null}
    </span>
  );
}

function BotonActualizar({ t }: { t: TramoVuelo }) {
  const actualizar = useActualizarVuelo();
  const { avisar } = useAvisos();
  return (
    <Boton
      variante="secundario"
      disabled={actualizar.isPending}
      aria-label={`Actualizar ahora el vuelo ${t.numero} del viaje ${t.codigo}`}
      onClick={() =>
        actualizar.mutate(t.id, {
          onSuccess: (r) => avisar({ tono: r.consultado ? "exito" : "aviso", texto: r.mensaje }),
          onError: (error) => avisar({ tono: "error", texto: error.message }),
        })
      }
    >
      {actualizar.isPending ? "Actualizando…" : "Actualizar ahora"}
    </Boton>
  );
}

export function PantallaVuelos({ fecha }: { fecha: string | null }) {
  const consulta = useVuelosDelDia(fecha);
  const datos = consulta.data;
  const titulo = fecha ? `Vuelos del ${fecha}` : datos ? `Vuelos de hoy (${datos.hoy}, UTC)` : "Vuelos de hoy";
  return (
    <div className="flex min-w-0 flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Operaciones" }, { texto: "Vuelos" }]}
        titulo={titulo}
        descripcion="Estado de cada tramo el día del viaje. Se consulta desde 3 horas antes de la salida hasta la llegada, con caché y topes para cuidar las búsquedas del plan; el viajero recibe un aviso por Telegram solo si algo cambia. Esta página se refresca cada 15 segundos mientras está a la vista."
      />
      <ElegirDia fecha={fecha} />
      {datos ? (
        datos.tramos.length === 0 ? (
          <EstadoVacio titulo={fecha ? "No hay vuelos registrados para este día" : "No hay vuelos hoy ni en curso"}>
            Los tramos se registran al decidir un viaje y se muestran el día del vuelo, cuando el viaje está aprobado.
          </EstadoVacio>
        ) : (
          <>
            <p role="status" className="text-sm text-texto-secundario">
              {datos.tramos.length} {datos.tramos.length === 1 ? "tramo" : "tramos"}. Las horas son locales de cada aeropuerto.
            </p>
            {/* En celular, tarjetas propias: el estado y la consulta son textos largos y necesitan todo el ancho. */}
            <ul aria-label={titulo} className="flex flex-col gap-3 md:hidden">
              {datos.tramos.map((t) => (
                <li key={t.id} className="flex flex-col gap-3 rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <span className="flex flex-col">
                      <span className="font-semibold">{t.numero}</span>
                      <span className="text-sm text-texto-secundario">
                        {t.aerolinea ?? "—"} · {t.sentido}
                      </span>
                    </span>
                    <Link href={`/viajes/${t.viaje_id}`} className="font-semibold">
                      {t.codigo}
                    </Link>
                  </div>
                  <RutaYHoras t={t} />
                  <Estado t={t} />
                  <Consulta t={t} />
                  <BotonActualizar t={t} />
                </li>
              ))}
            </ul>
            <div className="hidden md:block">
              <Tabla<TramoVuelo>
                titulo={titulo}
                filas={datos.tramos}
                claveFila={(t) => t.id}
                columnas={[
                  {
                    clave: "vuelo",
                    encabezado: "Vuelo",
                    principal: true,
                    celda: (t) => (
                      <span className="flex flex-col">
                        <span className="whitespace-nowrap font-semibold">{t.numero}</span>
                        <span className="text-sm text-texto-secundario">
                          {t.aerolinea ?? "—"} · {t.sentido}
                        </span>
                        <Link href={`/viajes/${t.viaje_id}`} className="relative z-10 whitespace-nowrap text-sm font-semibold">
                          {t.codigo}
                        </Link>
                        <span className="text-sm text-texto-secundario">{t.titular ?? "—"}</span>
                      </span>
                    ),
                  },
                  { clave: "ruta", encabezado: "Ruta y horas", celda: (t) => <RutaYHoras t={t} /> },
                  { clave: "estado", encabezado: "Estado", celda: (t) => <Estado t={t} /> },
                  { clave: "consulta", encabezado: "Consulta", celda: (t) => <Consulta t={t} /> },
                ]}
                acciones={(t) => <BotonActualizar t={t} />}
              />
            </div>
          </>
        )
      ) : consulta.error ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} volverA={{ href: "/viajes", texto: "Ir a viajes" }} />
      ) : (
        <EsqueletoLista texto="Cargando los vuelos…" />
      )}
    </div>
  );
}
