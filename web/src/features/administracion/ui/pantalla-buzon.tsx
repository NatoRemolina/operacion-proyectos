"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { estadoVisibleGasto } from "@/features/gastos/domain/gastos";
import { Boton } from "@/shared/ui/boton";
import { CampoSelector } from "@/shared/ui/campo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { Alerta, InsigniaEstado } from "@/shared/ui/estado";
import { EtiquetaEstado } from "@/shared/ui/etiqueta-estado";
import { useBuzon, useLeerBuzon } from "../application/administracion";
import type { BuzonSimulado } from "../domain/buzon";

const TARJETA = "rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta";
const TITULO = "Buzón de correo (simulado)";
const MIGAS = [{ texto: "Gastos", href: "/gastos" }, { texto: TITULO }];

function Lectura({ buzon }: { buzon: BuzonSimulado }) {
  const lectura = useLeerBuzon();
  const [elegidos, setElegidos] = useState<ReadonlySet<string>>(() => new Set(buzon.mensajes.map((m) => m.nombre)));
  const [viaje, setViaje] = useState("");
  const [sinElegir, setSinElegir] = useState(false);

  function alternar(nombre: string) {
    setSinElegir(false);
    setElegidos((previos) => {
      const siguientes = new Set(previos);
      if (siguientes.has(nombre)) siguientes.delete(nombre);
      else siguientes.add(nombre);
      return siguientes;
    });
  }

  function leer(evento: FormEvent) {
    evento.preventDefault();
    const nombres = buzon.mensajes.map((m) => m.nombre).filter((n) => elegidos.has(n));
    if (!nombres.length) {
      setSinElegir(true);
      return;
    }
    lectura.mutate({ nombres, viajeId: viaje ? Number(viaje) : null });
  }

  const error = lectura.error;
  const resultado = lectura.data;
  return (
    <>
      <form onSubmit={leer} noValidate className={`${TARJETA} flex flex-col gap-4`}>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-lg font-bold">Correos en el buzón</legend>
          {buzon.mensajes.length ? (
            <ul className="flex flex-col">
              {buzon.mensajes.map((m) => (
                <li key={m.nombre} className="border-b border-linea last:border-b-0">
                  <label className="flex min-h-11 cursor-pointer items-start gap-3 py-2">
                    <input
                      type="checkbox"
                      checked={elegidos.has(m.nombre)}
                      onChange={() => alternar(m.nombre)}
                      className="mt-1 size-5 shrink-0 accent-marca"
                    />
                    <span className="flex min-w-0 flex-col">
                      <span className="break-all font-semibold">{m.nombre}</span>
                      <span className="text-sm text-texto-secundario">
                        {m.formato === "correo"
                          ? `De: ${m.remitente ?? "remitente sin leer"} · Asunto: ${m.asunto ?? "sin asunto"}`
                          : "Confirmación guardada como página (HTML)"}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-texto-secundario">El buzón simulado está vacío.</p>
          )}
        </fieldset>
        <div className="max-w-md">
          <CampoSelector
            id="buzon-viaje"
            etiqueta="Viaje al que se cargan"
            ayuda="El viaje define el proyecto y la persona. Sin viaje, los gastos quedan a tu nombre y en revisión."
            value={viaje}
            onChange={(e) => setViaje(e.target.value)}
          >
            <option value="">Sin viaje</option>
            {buzon.viajes.map((v) => (
              <option key={v.id} value={String(v.id)}>
                {[v.codigo, v.titular, v.ida, v.estado_texto].filter(Boolean).join(" · ")}
              </option>
            ))}
          </CampoSelector>
        </div>
        <div className="flex flex-col gap-2">
          <Boton type="submit" className="self-start" disabled={lectura.isPending}>
            {lectura.isPending ? "Leyendo el buzón…" : "Leer el buzón (simulado)"}
          </Boton>
          <p aria-live="polite" className="text-sm font-semibold text-error">
            {sinElegir ? "Elige al menos un correo." : null}
          </p>
        </div>
      </form>

      {error ? (
        <Alerta tono="error" rol="alert" titulo="No se pudo leer el buzón">
          <p>{[error.message, ...Object.values(error.campos)].join(" ")}</p>
        </Alerta>
      ) : null}

      {resultado ? (
        <section aria-labelledby="titulo-resultado" className={`${TARJETA} flex flex-col gap-3`}>
          <h2 id="titulo-resultado" className="text-lg font-bold">
            Resultado de la lectura
          </h2>
          {resultado.leidos.length ? (
            <ul className="flex flex-col">
              {resultado.leidos.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-linea py-2 last:border-b-0">
                  <Link href={`/gastos/${g.id}`} className="inline-flex min-h-11 items-center font-semibold">
                    {g.comercio ?? `Gasto #${g.id}`}
                  </Link>
                  <EtiquetaEstado estado={estadoVisibleGasto(g.estado)} texto={g.estado_texto} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-texto-secundario">No se creó ningún gasto.</p>
          )}
          {resultado.errores.length ? (
            <ul className="flex flex-col gap-1">
              {resultado.errores.map((e) => (
                <li key={e.nombre} className="text-error">
                  <span aria-hidden="true">✕ </span>
                  {e.nombre}: {e.mensaje}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}
    </>
  );
}

/**
 * Buzón de correo simulado: administración lee los correos de ejemplo como si llegaran a un buzón de
 * gastos. Cada correo entra por el canal «correo» y se lee y valida como cualquier recibo.
 */
export function PantallaBuzon() {
  const consulta = useBuzon();
  const buzon = consulta.data;
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <EncabezadoPagina
        migas={MIGAS}
        titulo={TITULO}
        accion={<InsigniaEstado tono="aviso">Simulado</InsigniaEstado>}
        descripcion="Cada correo se lee como un recibo que llega por correo: lectura, validación y su estado real."
      />
      {buzon ? (
        <>
          <Alerta tono="info" titulo="Es una simulación">
            <p>{buzon.aviso}</p>
          </Alerta>
          <Lectura buzon={buzon} />
        </>
      ) : consulta.error ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : (
        <EsqueletoLista texto="Cargando el buzón…" />
      )}
    </div>
  );
}
