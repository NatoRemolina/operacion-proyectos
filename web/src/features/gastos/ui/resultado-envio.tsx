"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { Alerta } from "@/shared/ui/estado";
import { formatearDinero, formatearFecha } from "@/shared/ui/formato";
import { resultadoDeEnvio, type GastoDetalle } from "../domain/gastos";

/** Muestra el estado real que devolvió la plataforma; recibir un 201 no significa «aprobado». */
export function ResultadoEnvio({
  gasto,
  onEnviarOtro,
}: {
  gasto: GastoDetalle;
  onEnviarOtro: () => void;
}) {
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => titulo.current?.focus(), []);
  const resultado = resultadoDeEnvio(gasto.estado);

  return (
    <section aria-labelledby="titulo-resultado" className="flex flex-col gap-4">
      <h2 id="titulo-resultado" ref={titulo} tabIndex={-1} className="text-xl font-bold focus:outline-none">
        Recibo enviado
      </h2>
      {resultado === "aprobado" ? (
        <Alerta tono="exito" titulo="Aprobado">
          <p>
            {gasto.viaje
              ? `El gasto quedó aprobado y ya cuenta en el viaje ${gasto.viaje.codigo}.`
              : "El gasto quedó aprobado."}
          </p>
        </Alerta>
      ) : resultado === "revision" ? (
        <Alerta
          tono="aviso"
          titulo={
            gasto.justificaciones.length
              ? "En revisión: administración lo revisa con lo que contaste."
              : "En revisión: administración lo revisa. Si cuentas en el detalle para qué fue, se resuelve antes."
          }
        >
          {gasto.alertas.length > 0 ? (
            <ul className="list-disc pl-5">
              {gasto.alertas.map((alerta) => (
                <li key={alerta}>{alerta}</li>
              ))}
            </ul>
          ) : null}
        </Alerta>
      ) : (
        <Alerta tono="neutro" titulo={gasto.estado_texto}>
          <p>Recibimos el recibo. Su estado se actualizará en «Mis gastos».</p>
        </Alerta>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-tarjeta border border-linea bg-superficie p-4">
        <dt className="text-texto-secundario">Comercio</dt>
        <dd>{gasto.comercio ?? "Por confirmar"}</dd>
        <dt className="text-texto-secundario">Fecha</dt>
        <dd>{formatearFecha(gasto.fecha)}</dd>
        <dt className="text-texto-secundario">Total</dt>
        <dd className="tabular-nums">{formatearDinero(gasto.total, gasto.moneda)}</dd>
        <dt className="text-texto-secundario">Viaje</dt>
        <dd>{gasto.viaje?.codigo ?? "Sin viaje asignado"}</dd>
      </dl>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Link href={`/gastos/${gasto.id}`} className={clasesBoton("primario")}>
          Ver el detalle
        </Link>
        <Boton variante="secundario" onClick={onEnviarOtro}>
          Cargar otro gasto
        </Boton>
      </div>
    </section>
  );
}
