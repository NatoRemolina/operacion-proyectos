"use client";

import { useId, useRef, useState, type KeyboardEvent, type Ref } from "react";
import { useBuscarLugarAhora, useSugerenciasLugar } from "../application/cotizar";
import {
  agregarAeropuertos,
  ladoDesdeSugerencia,
  quitarAeropuerto,
  textoDistancia,
  type LadoElegido,
  type LugarSugerido,
  type ReglasCarretera,
} from "../domain/cotizar";
import { Marca } from "./piezas";

const CONTROL =
  "block min-h-11 w-full rounded-lg border border-borde-campo bg-superficie px-3 py-2 text-base text-texto " +
  "placeholder:text-texto-secundario aria-invalid:border-2 aria-invalid:border-error";

function donde(s: LugarSugerido): string {
  if (s.tipo === "aeropuerto") return [`Aeropuerto ${s.id}`, s.region, s.pais].filter(Boolean).join(", ");
  if (s.tipo === "pais") return "País: se proponen sus aeropuertos principales";
  return [s.region, s.pais].filter(Boolean).join(", ");
}

function aeropuertosDe(s: LugarSugerido): string {
  if (s.tipo !== "lugar" || s.aeropuertos.length === 0) return s.aviso ?? "";
  const lista = s.aeropuertos.map((a) => (a.km !== null ? `${a.iata} a ${Math.round(a.km)} km` : a.iata)).join(", ");
  return `Aeropuertos cercanos: ${lista}`;
}

/**
 * Combobox de lugares con el patrón de ARIA: flechas para moverse, Enter para elegir, Escape para cerrar.
 * Enter nunca envía el formulario con una búsqueda a medias: si la lista aún no llegó, elige la primera al llegar.
 */
function ComboLugar({
  id,
  etiqueta,
  nombreLista,
  texto,
  onTexto,
  onElegir,
  siempreEnter = false,
  ayudaId,
  error,
  entradaRef,
}: {
  id: string;
  etiqueta: string;
  nombreLista: string;
  texto: string;
  onTexto: (texto: string) => void;
  onElegir: (s: LugarSugerido, carretera: ReglasCarretera) => void;
  /** En «agregar otro aeropuerto», Enter nunca envía el formulario. */
  siempreEnter?: boolean;
  ayudaId?: string;
  error?: string | null;
  entradaRef?: Ref<HTMLInputElement>;
}) {
  const sugerencias = useSugerenciasLugar(texto);
  const buscarAhora = useBuscarLugarAhora();
  const [abierta, setAbierta] = useState(false);
  const [activo, setActivo] = useState(-1);
  const [eligiendo, setEligiendo] = useState(false);
  const listaId = `${id}-lista`;
  const { resultados } = sugerencias;
  const visible = abierta && texto.trim().length >= 2;
  const activoValido = activo < resultados.length ? activo : -1;

  function elegir(s: LugarSugerido | undefined, carretera: ReglasCarretera = sugerencias.carretera) {
    setAbierta(false);
    setActivo(-1);
    if (s) onElegir(s, carretera);
  }

  async function elegirAlLlegar() {
    setEligiendo(true);
    try {
      const lista = await buscarAhora(texto);
      elegir(lista.resultados[0], lista.carretera);
    } catch {
      // Sin respuesta: el campo sigue con el texto escrito y la persona puede reintentar.
    } finally {
      setEligiendo(false);
    }
  }

  function alPresionar(e: KeyboardEvent<HTMLInputElement>) {
    const hayLista = visible && resultados.length > 0;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setAbierta(true);
      if (resultados.length) setActivo(Math.min(activoValido + 1, resultados.length - 1));
    } else if (e.key === "ArrowUp" && hayLista) {
      e.preventDefault();
      setActivo(Math.max(activoValido - 1, 0));
    } else if (e.key === "Enter") {
      const escrito = texto.trim().length >= 2;
      if (hayLista && sugerencias.listo) {
        e.preventDefault();
        elegir(resultados[activoValido >= 0 ? activoValido : 0]);
      } else if (escrito && (abierta || siempreEnter)) {
        e.preventDefault();
        void elegirAlLlegar();
      } else if (siempreEnter) {
        e.preventDefault();
      }
    } else if (e.key === "Escape" && visible) {
      e.preventDefault();
      setAbierta(false);
    }
  }

  const describe = [ayudaId, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="relative flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">
        {etiqueta}
      </label>
      <input
        id={id}
        ref={entradaRef}
        className={CONTROL}
        value={texto}
        autoComplete="off"
        spellCheck={false}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={visible && sugerencias.resultados.length > 0}
        aria-controls={listaId}
        aria-activedescendant={visible && activoValido >= 0 ? `${listaId}-${activoValido}` : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={describe}
        aria-busy={eligiendo || undefined}
        onChange={(e) => {
          onTexto(e.target.value);
          setAbierta(true);
          setActivo(-1);
        }}
        onKeyDown={alPresionar}
        onBlur={() => setAbierta(false)}
      />
      {error ? (
        <p id={`${id}-error`} className="text-sm font-semibold text-error">
          <span aria-hidden="true">✕ </span>
          {error}
        </p>
      ) : null}
      <div
        className={`se-mueve absolute inset-x-0 top-full z-20 mt-1 origin-top overflow-hidden rounded-tarjeta border border-linea bg-superficie shadow-lg transition-[opacity,transform] duration-150 ease-out starting:scale-y-95 starting:opacity-0 motion-reduce:starting:scale-y-100 ${
          visible ? "" : "hidden"
        }`}
      >
        <ul id={listaId} role="listbox" aria-label={nombreLista} className="max-h-96 overflow-y-auto py-1">
          {resultados.map((s, i) => (
            <li
              key={`${s.origen}-${s.tipo}-${s.id}`}
              id={`${listaId}-${i}`}
              role="option"
              aria-selected={i === activoValido}
              className={`cursor-pointer border-b border-linea px-3 py-2 last:border-b-0 ${
                i === activoValido ? "bg-marca-suave" : "hover:bg-neutro-suave"
              }`}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => elegir(s)}
            >
              <span className="flex flex-wrap items-center gap-2 font-semibold">
                {s.nombre}
                {s.tambien ? <span className="font-normal text-texto-secundario">también {s.tambien}</span> : null}
                {s.origen === "google" ? <Marca>Google</Marca> : null}
              </span>
              {donde(s) ? <span className="block text-sm text-texto-secundario">{donde(s)}</span> : null}
              {aeropuertosDe(s) ? <span className="block text-sm text-texto-secundario">{aeropuertosDe(s)}</span> : null}
            </li>
          ))}
        </ul>
        <p aria-live="polite" className="px-3 pb-2 text-sm text-texto-secundario empty:hidden">
          {sugerencias.esperando && resultados.length === 0
            ? "Buscando lugares…"
            : sugerencias.listo && resultados.length === 0
              ? "Sin coincidencias. Prueba con otro nombre o con el código del aeropuerto."
              : ""}
          {sugerencias.avisoGoogle ? ` ${sugerencias.avisoGoogle}` : ""}
        </p>
      </div>
    </div>
  );
}

/**
 * Campo de origen o destino como el de un buscador de vuelos: un país, una ciudad, un pueblo o un código.
 * Al elegir, propone los aeropuertos cercanos con su distancia; se pueden quitar y agregar otros.
 */
export function CampoLugar({
  id,
  etiqueta,
  lado,
  valor,
  onCambio,
  error,
  entradaRef,
}: {
  id: string;
  etiqueta: string;
  lado: "origen" | "destino";
  valor: LadoElegido;
  onCambio: (valor: LadoElegido) => void;
  error?: string | null;
  entradaRef?: Ref<HTMLInputElement>;
}) {
  const agregarRef = useRef<HTMLInputElement>(null);
  const ayudaId = useId();
  const delLado = lado === "origen" ? "el origen" : "el destino";
  const n = valor.aeropuertos.length;
  const ayuda = !valor.elegido
    ? "Escribe y elige de la lista: se proponen los aeropuertos cercanos."
    : n === 0
      ? "Sin aeropuertos para comparar. Agrega uno por nombre o código."
      : n === 1
        ? "Se compara 1 aeropuerto."
        : `Se comparan ${n} aeropuertos en una sola búsqueda.`;

  return (
    <div className="flex flex-col gap-2">
      <ComboLugar
        id={id}
        etiqueta={etiqueta}
        nombreLista={`Sugerencias para ${etiqueta.toLowerCase()}`}
        texto={valor.texto}
        onTexto={(texto) => onCambio({ texto, lugar: null, aeropuertos: [], elegido: false })}
        onElegir={(s) => onCambio(ladoDesdeSugerencia(s))}
        ayudaId={ayudaId}
        error={error}
        entradaRef={entradaRef}
      />
      <p id={ayudaId} aria-live="polite" className="text-sm text-texto-secundario">
        {ayuda}
      </p>
      {valor.elegido ? (
        <div className="flex flex-col gap-3 rounded-tarjeta border border-linea bg-fondo p-3">
          {n > 0 ? (
            <ul aria-label={`Aeropuertos que se comparan en ${delLado}`} className="flex flex-col gap-2">
              {valor.aeropuertos.map((a) => (
                <li key={a.iata} className="flex items-center gap-3 rounded-lg bg-superficie px-3 py-2">
                  <span className="text-lg font-extrabold tracking-wide">{a.iata}</span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate">{a.nombre ?? a.iata}</span>
                    {textoDistancia(a) ? (
                      <span className="text-sm text-texto-secundario">{textoDistancia(a)}</span>
                    ) : null}
                  </span>
                  {a.origen === "google" ? <Marca>Google</Marca> : null}
                  <button
                    type="button"
                    aria-label={`Quitar ${a.iata}`}
                    className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg px-2 font-semibold text-marca underline underline-offset-3 hover:text-marca-oscura se-mueve motion-safe:active:scale-[0.97]"
                    onClick={() => onCambio(quitarAeropuerto(valor, a.iata))}
                  >
                    Quitar
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <ComboLugar
            id={`${id}-agregar`}
            etiqueta={`Agregar otro aeropuerto a${lado === "origen" ? "l origen" : "l destino"}`}
            nombreLista={`Aeropuertos para agregar a ${delLado}`}
            texto={valor.agregando ?? ""}
            onTexto={(texto) => onCambio({ ...valor, agregando: texto })}
            onElegir={(s, carretera) => {
              onCambio(agregarAeropuertos(valor, s, carretera));
              agregarRef.current?.focus();
            }}
            siempreEnter
            entradaRef={agregarRef}
          />
        </div>
      ) : null}
    </div>
  );
}
