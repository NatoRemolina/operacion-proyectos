"use client";

import { useState, type FormEvent } from "react";
import { Boton } from "@/shared/ui/boton";
import { CampoAreaTexto } from "@/shared/ui/campo";
import { Alerta } from "@/shared/ui/estado";
import { formatearInstante } from "@/shared/ui/formato";
import { useJustificacion } from "../application/gastos";
import { JUSTIFICACION_MAXIMO, type GastoDetalle, type Justificacion } from "../domain/gastos";

const CANAL: Record<string, string> = {
  web: "web",
  celular: "celular",
  telegram: "Telegram",
  api: "esta aplicación",
};

function Entrada({ j }: { j: Justificacion }) {
  const forma = j.tipo === "audio" ? "Nota de voz" : "Por escrito";
  return (
    <li className="border-b border-linea py-3 last:border-b-0">
      <p className="text-sm text-texto-secundario">
        {forma} · desde {CANAL[j.canal] ?? j.canal} · {formatearInstante(j.creado)}
      </p>
      {j.texto ? <p className="mt-1">{j.texto}</p> : null}
      {j.tipo === "audio" && j.transcripcion === "pendiente" ? (
        <p className="mt-1 text-sm text-texto-secundario">La transcripción está pendiente; el audio quedó guardado.</p>
      ) : null}
      {j.tipo === "audio" && j.transcripcion === "fallida" ? (
        <p className="mt-1 text-sm text-texto-secundario">No se pudo transcribir; el audio quedó guardado para revisarlo.</p>
      ) : null}
    </li>
  );
}

/** Lo que la persona contó del gasto y el formulario para añadir algo más. */
export function JustificacionGasto({ gasto }: { gasto: GastoDetalle }) {
  const [texto, setTexto] = useState("");
  const accion = useJustificacion(gasto.id);
  const hay = gasto.justificaciones.length > 0;

  function guardar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    accion.justificar(texto, () => setTexto(""));
  }

  const errorServidor =
    accion.error?.tipo === "prohibido"
      ? "Solo quien hizo el gasto o quien viaja puede justificarlo."
      : accion.error?.tipo === "validacion"
        ? (Object.values(accion.error.campos)[0] ?? accion.error.message)
        : (accion.error?.message ?? null);

  return (
    <section aria-labelledby="titulo-justificacion" className="rounded-tarjeta border border-linea bg-superficie p-4">
      <h2 id="titulo-justificacion" className="text-lg font-bold">
        Para qué fue
      </h2>
      {hay ? (
        <ul className="mt-1">
          {gasto.justificaciones.map((j) => (
            <Entrada key={j.id} j={j} />
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-texto-secundario">
          {gasto.estado === "revision"
            ? "Aún no has contado para qué fue. Hacerlo ayuda a resolver la revisión."
            : "Aún no has contado para qué fue este gasto."}
        </p>
      )}

      <form onSubmit={guardar} className="mt-4 flex flex-col gap-3 border-t border-linea pt-4">
        <CampoAreaTexto
          id="nueva-justificacion"
          etiqueta={hay ? "Añadir algo más" : "¿Para qué fue este gasto?"}
          ayuda="Con tus palabras. Para dejar una nota de voz, respóndele al bot de Telegram."
          placeholder="Por ejemplo: cena con el equipo de grabación después de la jornada en el lago"
          maxLength={JUSTIFICACION_MAXIMO}
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value);
            if (accion.errorTexto || accion.error) accion.limpiar();
          }}
          error={accion.errorTexto}
          disabled={accion.guardando}
        />
        {errorServidor ? <Alerta tono="error" titulo={errorServidor} rol="alert" /> : null}
        <p role="status" aria-live="polite" className="sr-only">
          {accion.guardando ? "Guardando la justificación…" : accion.guardada ? "Justificación guardada." : ""}
        </p>
        <Boton type="submit" disabled={accion.guardando} className="self-start">
          {accion.guardando ? "Guardando…" : "Guardar"}
        </Boton>
      </form>
    </section>
  );
}
