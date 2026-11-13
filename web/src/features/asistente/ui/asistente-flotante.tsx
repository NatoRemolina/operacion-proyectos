"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { usePermiso, usePersonaId } from "@/shared/application/identidad";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { Distintivo } from "@/shared/ui/distintivo";
import { PRESIONAR } from "@/shared/ui/movimiento";
import { useConversacion, useTranscribir, type Mensaje } from "../application/asistente";
import { useGrabadora, vozSoportada } from "../application/grabadora";
import {
  ESPERA_LARGA_S,
  MAX_GRABACION_S,
  MAX_PREGUNTA,
  PREGUNTAS_SUGERIDAS,
  bloquesDeTexto,
  duracionLegible,
  esDeIa,
  reloj,
  rutaDeFuente,
  type RespuestaAsistente,
  type Segmento,
} from "../domain/asistente";
import { IconoCerrar, IconoChispa, IconoDetener, IconoEnviar, IconoMicrofono, IconoNueva } from "./iconos";

/**
 * Asistente de IA flotante: un botón fijo abajo a la derecha en todas las pantallas de administración que
 * abre una conversación sin salir de la pantalla. Se pregunta por escrito o con la voz (se transcribe y se
 * envía). Para otros permisos no se muestra; la API además lo rechaza.
 */
export function AsistenteFlotante() {
  const permiso = usePermiso();
  const personaId = usePersonaId();
  if (permiso !== "admin") return null;
  return <Asistente key={personaId} />;
}

function Asistente() {
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const [transcribiendo, setTranscribiendo] = useState(false);
  const [avisoVoz, setAvisoVoz] = useState<string | null>(null);
  const [vistos, setVistos] = useState(0);
  const [conVoz] = useState(vozSoportada);
  const { mensajes, esperandoDesde, preguntar, reiniciar, cuenta } = useConversacion();
  const transcribir = useTranscribir();
  const boton = useRef<HTMLButtonElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);
  const historial = useRef<HTMLDivElement>(null);
  const controlVoz = useRef<AbortController | null>(null);
  const idPanel = useId();
  const idTitulo = useId();
  const idCampo = useId();

  const enviar = useCallback(
    (pregunta: string, porVoz = false) => {
      if (!pregunta.trim()) return;
      setAvisoVoz(null);
      if (!porVoz) setTexto("");
      void preguntar(pregunta, porVoz);
    },
    [preguntar],
  );

  const grabadora = useGrabadora({
    alTerminar: async (wav) => {
      setTranscribiendo(true);
      const abortar = new AbortController();
      controlVoz.current = abortar;
      try {
        const dicho = await transcribir(wav, abortar.signal);
        if (dicho.trim()) enviar(dicho, true);
        else setAvisoVoz("No se entendió el audio. Acércate al micrófono e intenta de nuevo, o escribe la pregunta.");
      } catch (causa) {
        if (!abortar.signal.aborted) {
          const error = causa as ErrorDeAplicacion;
          setAvisoVoz(
            error.tipo === "sesion_vencida" || error.tipo === "red"
              ? error.message
              : "La voz no está disponible en este momento. Escribe la pregunta.",
          );
        }
      } finally {
        if (controlVoz.current === abortar) controlVoz.current = null;
        setTranscribiendo(false);
        campo.current?.focus();
      }
    },
    alFallar: (mensaje) => setAvisoVoz(mensaje),
  });

  const grabando = grabadora.estado === "pidiendo" || grabadora.estado === "grabando";
  const procesandoVoz = grabadora.estado === "procesando" || transcribiendo;
  const ocupado = esperandoDesde !== null || grabando || procesandoVoz;
  const novedad = !abierto && mensajes.slice(vistos).some((m) => m.rol !== "persona");

  const abrir = () => {
    setAbierto(true);
    setVistos(mensajes.length);
  };
  const cerrar = useCallback(() => {
    setAbierto(false);
    setVistos(mensajes.length);
    boton.current?.focus();
  }, [mensajes.length]);

  const cancelarVoz = useCallback(() => {
    grabadora.cancelar();
    controlVoz.current?.abort();
    controlVoz.current = null;
    setTranscribiendo(false);
    campo.current?.focus();
  }, [grabadora]);

  useEffect(() => {
    if (abierto) campo.current?.focus();
  }, [abierto]);

  useEffect(() => {
    if (!abierto) return;
    // Escape cierra desde cualquier parte (también si el foco quedó fuera del panel); grabando, solo cancela.
    const alTeclear = (evento: globalThis.KeyboardEvent) => {
      if (evento.key !== "Escape" || evento.defaultPrevented) return;
      evento.preventDefault();
      if (grabando || procesandoVoz) cancelarVoz();
      else cerrar();
    };
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [abierto, grabando, procesandoVoz, cancelarVoz, cerrar]);

  useEffect(() => {
    const h = historial.current;
    if (h) h.scrollTop = h.scrollHeight;
  }, [mensajes.length, esperandoDesde, abierto]);

  const alEnviar = (evento: FormEvent) => {
    evento.preventDefault();
    if (!ocupado) enviar(texto);
  };
  const alTeclearCampo = (evento: KeyboardEvent<HTMLTextAreaElement>) => {
    if (evento.key === "Enter" && !evento.shiftKey && !evento.nativeEvent.isComposing) {
      evento.preventDefault();
      if (!ocupado) enviar(texto);
    }
  };
  const elegir = (pregunta: string) => {
    enviar(pregunta);
    campo.current?.focus(); // el botón elegido desaparece: el foco no se pierde
  };
  const dictar = () => {
    setAvisoVoz(null);
    void grabadora.empezar();
  };
  const alAbrirFuente = () => {
    if (window.matchMedia("(max-width: 47.99rem)").matches) setAbierto(false); // en celular el panel tapa la pantalla
  };

  const anuncio = grabando
    ? "Grabando tu pregunta. Pulsa Listo para enviarla."
    : procesandoVoz
      ? "Transcribiendo tu voz."
      : esperandoDesde !== null
        ? "El asistente está consultando los datos."
        : novedad
          ? "El asistente respondió. Abre el asistente para leerlo."
          : "";

  return (
    <>
      <p role="status" className="sr-only">
        {anuncio}
      </p>

      <button
        ref={boton}
        type="button"
        onClick={() => (abierto ? cerrar() : abrir())}
        aria-expanded={abierto}
        aria-controls={idPanel}
        className={`fondo-ia fixed bottom-20 right-4 z-40 flex min-h-14 min-w-14 items-center justify-center gap-2 rounded-full px-4 text-sobre-marca shadow-lg shadow-grafito/25 md:bottom-6 md:right-6 md:px-5 ${PRESIONAR} ${
          abierto ? "max-md:hidden" : ""
        }`}
      >
        <IconoChispa className="size-6 text-cian-claro" />
        <span className="font-bold max-md:sr-only">Asistente IA</span>
        {novedad ? (
          <span className="absolute right-1 top-1 size-3.5 rounded-full border-2 border-superficie bg-aviso" aria-hidden="true" />
        ) : null}
      </button>

      <section
        id={idPanel}
        role="dialog"
        aria-modal="false"
        aria-labelledby={idTitulo}
        hidden={!abierto}
        className="entrada-ia se-mueve fixed inset-x-0 bottom-0 z-40 flex h-[85dvh] flex-col overflow-hidden rounded-t-2xl border border-linea bg-superficie shadow-2xl shadow-grafito/30 md:inset-x-auto md:bottom-24 md:right-6 md:h-auto md:max-h-[min(42rem,calc(100dvh-8rem))] md:w-[26rem] md:rounded-2xl [@media(max-height:30rem)]:overflow-y-auto"
      >
        <div className="zona-oscura fondo-ia flex shrink-0 items-center gap-3 py-2.5 pl-4 pr-2 text-sobre-grafito">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-sobre-grafito/10 ring-1 ring-sobre-grafito/25">
            <IconoChispa className="size-5 text-cian-claro" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={idTitulo} className="text-base font-bold leading-tight">
              Asistente IA
            </h2>
            <p className="flex items-center gap-1.5 truncate text-xs text-sobre-grafito-suave">
              <span className="inline-block size-2 shrink-0 rounded-full bg-cian-claro" aria-hidden="true" />
              Con datos de la plataforma
            </p>
          </div>
          {mensajes.length > 0 ? (
            <button
              type="button"
              onClick={() => {
                reiniciar();
                campo.current?.focus();
              }}
              aria-label="Empezar una conversación nueva"
              title="Conversación nueva"
              className={`grid size-11 shrink-0 place-items-center rounded-xl text-sobre-grafito hover:bg-sobre-grafito/10 ${PRESIONAR}`}
            >
              <IconoNueva className="size-5" />
            </button>
          ) : null}
          <button
            type="button"
            onClick={cerrar}
            aria-label="Cerrar el asistente"
            title="Cerrar"
            className={`grid size-11 shrink-0 place-items-center rounded-xl text-sobre-grafito hover:bg-sobre-grafito/10 ${PRESIONAR}`}
          >
            <IconoCerrar className="size-5" />
          </button>
        </div>

        <div
          ref={historial}
          role="log"
          aria-live="polite"
          aria-label="Conversación con el asistente"
          className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-fondo px-3 py-4 sm:px-4"
        >
          {mensajes.length === 0 ? (
            <Bienvenida conVoz={conVoz} deshabilitado={ocupado} onElegir={elegir} />
          ) : (
            <ol className="space-y-4">
              {mensajes.map((m) => (
                <li key={m.id}>
                  <VistaMensaje mensaje={m} ocupado={ocupado} onReintentar={elegir} onAbrirFuente={alAbrirFuente} />
                </li>
              ))}
            </ol>
          )}
          {esperandoDesde !== null ? <Pensando desde={esperandoDesde} /> : null}
        </div>

        <form onSubmit={alEnviar} className="shrink-0 border-t border-linea bg-superficie px-3 pb-3 pt-2.5">
          {avisoVoz ? (
            <div role="alert" className="mb-2 flex items-start gap-2 rounded-xl border border-aviso bg-aviso-suave py-2 pl-3 pr-1 text-sm text-texto">
              <p className="flex-1 py-1">{avisoVoz}</p>
              <button
                type="button"
                onClick={() => setAvisoVoz(null)}
                aria-label="Cerrar el aviso"
                className="grid size-9 shrink-0 place-items-center rounded-lg text-texto-secundario hover:bg-superficie"
              >
                <IconoCerrar className="size-4" />
              </button>
            </div>
          ) : null}

          {grabando ? (
            <BarraGrabacion
              pidiendo={grabadora.estado === "pidiendo"}
              segundos={grabadora.segundos}
              nivel={grabadora.nivel}
              onCancelar={cancelarVoz}
              onListo={grabadora.detener}
            />
          ) : procesandoVoz ? (
            <div className="flex min-h-14 items-center gap-3 rounded-2xl border border-linea bg-marca-suave px-3">
              <span className="size-5 shrink-0 animate-spin rounded-full border-2 border-marca border-t-transparent" aria-hidden="true" />
              <p className="flex-1 text-sm font-bold text-marca">Transcribiendo tu voz…</p>
              <button
                type="button"
                onClick={cancelarVoz}
                className="min-h-11 rounded-xl px-3 text-sm font-bold text-texto-secundario hover:bg-superficie"
              >
                Cancelar
              </button>
            </div>
          ) : (
            <div className="flex items-end gap-1.5 rounded-2xl border border-borde-campo bg-superficie p-1.5 focus-within:border-marca focus-within:ring-2 focus-within:ring-marca">
              <label htmlFor={idCampo} className="sr-only">
                Tu pregunta para el asistente
              </label>
              <textarea
                ref={campo}
                id={idCampo}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onKeyDown={alTeclearCampo}
                rows={1}
                maxLength={MAX_PREGUNTA}
                placeholder="Escribe tu pregunta…"
                className="max-h-32 min-h-11 flex-1 resize-none bg-transparent px-2.5 py-2.5 text-base text-texto placeholder:text-texto-secundario focus:outline-none [field-sizing:content]"
              />
              {conVoz ? (
                <button
                  type="button"
                  onClick={dictar}
                  disabled={ocupado}
                  aria-label="Dictar la pregunta con la voz"
                  title="Dictar con la voz"
                  className={`grid size-11 shrink-0 place-items-center rounded-xl text-texto-secundario hover:bg-marca-suave hover:text-marca disabled:opacity-40 ${PRESIONAR}`}
                >
                  <IconoMicrofono className="size-5" />
                </button>
              ) : null}
              <button
                type="submit"
                disabled={ocupado || !texto.trim()}
                aria-label="Enviar la pregunta"
                title="Enviar"
                className={`fondo-ia grid size-11 shrink-0 place-items-center rounded-xl text-sobre-marca shadow-sm disabled:opacity-40 ${PRESIONAR}`}
              >
                <IconoEnviar className="size-5" />
              </button>
            </div>
          )}

          <p className="mt-2 flex flex-wrap justify-between gap-x-3 gap-y-0.5 px-1 text-xs text-texto-secundario">
            <span>La IA puede equivocarse: revisa las fuentes.</span>
            {cuenta ? (
              <span>
                {cuenta.usadas} de {cuenta.tope} preguntas hoy
              </span>
            ) : null}
          </p>
        </form>
      </section>
    </>
  );
}

function Bienvenida({ conVoz, deshabilitado, onElegir }: { conVoz: boolean; deshabilitado: boolean; onElegir: (p: string) => void }) {
  return (
    <div className="flex flex-col items-center px-1 pb-1 pt-3 text-center">
      <span className="fondo-ia grid size-14 place-items-center rounded-2xl shadow-md shadow-grafito/20">
        <IconoChispa className="size-7 text-cian-claro" />
      </span>
      <p className="mt-3 text-lg font-bold text-texto">¿En qué te ayudo?</p>
      <p className="mt-1 max-w-xs text-sm text-texto-secundario">
        Pregunta por viajes, gastos, cotizaciones o indicadores{conVoz ? ", por escrito o con tu voz" : ""}. Cada respuesta cita de
        dónde salen los datos.
      </p>
      <ul className="mt-4 w-full space-y-2 text-left" aria-label="Preguntas sugeridas">
        {PREGUNTAS_SUGERIDAS.map((p) => (
          <li key={p}>
            <button
              type="button"
              onClick={() => onElegir(p)}
              disabled={deshabilitado}
              className={`flex min-h-11 w-full items-center gap-3 rounded-xl border border-linea bg-superficie px-3.5 py-2.5 text-left text-sm font-semibold text-texto shadow-sm hover:border-marca hover:bg-marca-suave disabled:opacity-50 ${PRESIONAR}`}
            >
              <IconoChispa className="size-4 shrink-0 text-marca" />
              {p}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Avatar() {
  return (
    <span className="fondo-ia mt-0.5 grid size-8 shrink-0 place-items-center rounded-full shadow-sm" aria-hidden="true">
      <IconoChispa className="size-4 text-cian-claro" />
    </span>
  );
}

function VistaMensaje({
  mensaje: m,
  ocupado,
  onReintentar,
  onAbrirFuente,
}: {
  mensaje: Mensaje;
  ocupado: boolean;
  onReintentar: (pregunta: string) => void;
  onAbrirFuente: () => void;
}) {
  if (m.rol === "persona") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-marca px-4 py-2.5 text-sobre-marca shadow-sm">
          <p className="sr-only">Tú:</p>
          {m.porVoz ? (
            <p className="mb-0.5 flex items-center gap-1 text-xs font-bold">
              <IconoMicrofono className="size-3.5" /> Dictado por voz
            </p>
          ) : null}
          <p className="whitespace-pre-line">{m.texto}</p>
          {m.estado === "perdida" ? (
            <p className="mt-1 text-xs">Sin respuesta: la página se recargó antes de que terminara.</p>
          ) : null}
        </div>
      </div>
    );
  }
  if (m.rol === "error") {
    const reintentable = m.tipo !== "prohibido" && m.tipo !== "sesion_vencida";
    return (
      <div className="flex gap-2.5">
        <Avatar />
        <div className="min-w-0 rounded-2xl rounded-tl-md border border-error bg-error-suave px-4 py-3 text-sm">
          <p className="font-bold text-error">No pude responder</p>
          <p className="mt-0.5 text-texto">{m.texto}</p>
          {reintentable ? (
            <button
              type="button"
              onClick={() => onReintentar(m.pregunta)}
              disabled={ocupado}
              className="mt-1 min-h-11 font-bold text-marca underline underline-offset-4 disabled:opacity-50"
            >
              Reintentar
            </button>
          ) : null}
        </div>
      </div>
    );
  }
  return <VistaRespuesta respuesta={m.respuesta} onAbrirFuente={onAbrirFuente} />;
}

function VistaRespuesta({ respuesta: r, onAbrirFuente }: { respuesta: RespuestaAsistente; onAbrirFuente: () => void }) {
  const fuentes = r.fuentes.map((f) => ({ ...f, ruta: rutaDeFuente(f.destino) }));
  return (
    <div className="flex gap-2.5">
      <Avatar />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-md border border-linea bg-superficie px-4 py-3 shadow-sm">
        <p className="sr-only">El asistente:</p>
        <TextoRespuesta texto={r.texto} />
        {fuentes.length > 0 ? (
          <div className="mt-3 border-t border-linea pt-2.5">
            <p className="text-xs font-bold uppercase tracking-wide text-texto-secundario">Fuentes</p>
            <ul className="mt-1.5 flex flex-wrap gap-1.5">
              {fuentes.map((f) => (
                <li key={`${f.tipo}-${f.codigo}`}>
                  {f.ruta ? (
                    <Link
                      href={f.ruta}
                      onClick={onAbrirFuente}
                      className="inline-flex min-h-11 items-center rounded-full border border-marca bg-marca-suave px-3 text-sm font-bold text-marca no-underline hover:bg-marca hover:text-sobre-marca"
                    >
                      {f.codigo}
                    </Link>
                  ) : (
                    <span className="inline-flex min-h-11 items-center rounded-full border border-linea bg-neutro-suave px-3 text-sm font-bold text-neutro">
                      {f.codigo}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-texto-secundario">
          <Distintivo tono={esDeIa(r.modo) ? "marca" : r.modo === "tope" ? "aviso" : "neutro"}>{r.modo_texto}</Distintivo>
          {r.duracion_ms > 0 ? <span>{duracionLegible(r.duracion_ms)}</span> : null}
          {r.herramientas.length > 0 ? (
            <span title={r.herramientas.join(" → ")}>
              · {r.herramientas.length} {r.herramientas.length === 1 ? "consulta" : "consultas"}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Segmentos({ segmentos }: { segmentos: readonly Segmento[] }) {
  return (
    <>
      {segmentos.map((s, i) =>
        s.negrita ? (
          <strong key={i} className="font-bold text-texto">
            {s.texto}
          </strong>
        ) : (
          <span key={i}>{s.texto}</span>
        ),
      )}
    </>
  );
}

function TextoRespuesta({ texto }: { texto: string }) {
  return (
    <div className="space-y-2 text-[0.9375rem] leading-relaxed text-texto">
      {bloquesDeTexto(texto).map((b, i) => {
        if (b.tipo === "parrafo") {
          return (
            <p key={i}>
              <Segmentos segmentos={b.segmentos} />
            </p>
          );
        }
        const Lista = b.ordenada ? "ol" : "ul";
        return (
          <Lista key={i} className={`space-y-1 pl-5 marker:text-marca ${b.ordenada ? "list-decimal" : "list-disc"}`}>
            {b.items.map((item, j) => (
              <li key={j}>
                <Segmentos segmentos={item} />
              </li>
            ))}
          </Lista>
        );
      })}
    </div>
  );
}

function Pensando({ desde }: { desde: number }) {
  const [ahora, setAhora] = useState(desde);
  useEffect(() => {
    const temporizador = window.setInterval(() => setAhora(Date.now()), 1000);
    return () => window.clearInterval(temporizador);
  }, []);
  const segundos = Math.max(0, Math.floor((ahora - desde) / 1000));
  return (
    <div className="mt-4 flex gap-2.5">
      <Avatar />
      <div className="rounded-2xl rounded-tl-md border border-linea bg-superficie px-4 py-3 shadow-sm">
        <div className="flex items-center gap-2.5">
          <span className="flex gap-1" aria-hidden="true">
            <span className="punto-ia" />
            <span className="punto-ia" />
            <span className="punto-ia" />
          </span>
          <span className="text-sm font-bold text-texto">Consultando los datos</span>
          <span className="text-xs tabular-nums text-texto-secundario" aria-hidden="true">
            {segundos} s
          </span>
        </div>
        {segundos >= ESPERA_LARGA_S ? (
          <p className="mt-1 text-xs text-texto-secundario">El asesor está revisando varias fuentes; puede tardar hasta un minuto.</p>
        ) : null}
      </div>
    </div>
  );
}

const FORMA_ONDA = [0.45, 0.7, 1, 0.8, 0.55, 0.9, 0.6];

function BarraGrabacion({
  pidiendo,
  segundos,
  nivel,
  onCancelar,
  onListo,
}: {
  pidiendo: boolean;
  segundos: number;
  nivel: number;
  onCancelar: () => void;
  onListo: () => void;
}) {
  return (
    <div className="flex min-h-14 items-center gap-2 rounded-2xl border border-error bg-error-suave py-1.5 pl-3 pr-1.5">
      <span className="relative flex size-3 shrink-0" aria-hidden="true">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-error opacity-60" />
        <span className="relative inline-flex size-3 rounded-full bg-error" />
      </span>
      <span className="text-sm font-bold text-error">{pidiendo ? "Activando el micrófono…" : "Escuchando"}</span>
      <span className="flex h-8 flex-1 items-center justify-center gap-1 max-[22rem]:hidden" aria-hidden="true">
        {FORMA_ONDA.map((forma, i) => (
          <span
            key={i}
            className="w-1 rounded-full bg-error transition-[height] duration-100"
            style={{ height: `${Math.round(4 + forma * nivel * 24)}px` }}
          />
        ))}
      </span>
      <span className="text-xs tabular-nums text-texto" aria-hidden="true">
        {reloj(segundos)} / {reloj(MAX_GRABACION_S)}
      </span>
      <button
        type="button"
        onClick={onCancelar}
        aria-label="Cancelar la grabación"
        title="Cancelar"
        className="grid size-11 shrink-0 place-items-center rounded-xl text-texto-secundario hover:bg-superficie"
      >
        <IconoCerrar className="size-5" />
      </button>
      <button
        type="button"
        onClick={onListo}
        disabled={pidiendo}
        className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl bg-error px-3 text-sm font-bold text-sobre-marca disabled:opacity-50 ${PRESIONAR}`}
      >
        <IconoDetener className="size-4" /> Listo
      </button>
    </div>
  );
}
