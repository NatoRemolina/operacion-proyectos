"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type TipoError } from "@/shared/domain/errores";
import { esRespuestaAsistente, type AsistenteRepository, type RespuestaAsistente } from "../domain/asistente";

const contexto = crearContextoRepositorio<AsistenteRepository>("AsistenteRepository");
export const AsistenteRepositoryProvider = contexto.Proveedor;
export const useAsistenteRepository = contexto.useRepositorio;

export type Mensaje =
  | {
      readonly id: string;
      readonly rol: "persona";
      readonly texto: string;
      readonly porVoz: boolean;
      /** `esperando` mientras responde; `perdida` si la página se recargó antes de la respuesta. */
      readonly estado: "esperando" | "respondida" | "perdida";
    }
  | { readonly id: string; readonly rol: "asistente"; readonly respuesta: RespuestaAsistente }
  | { readonly id: string; readonly rol: "error"; readonly texto: string; readonly tipo: TipoError; readonly pregunta: string };

const MAX_MENSAJES = 30;
const VERSION = 1;

function claveDe(personaId: number) {
  return `asistente:v${VERSION}:${personaId}`;
}

function esMensaje(m: unknown): m is Mensaje {
  if (!m || typeof m !== "object") return false;
  const x = m as Record<string, unknown>;
  if (typeof x.id !== "string") return false;
  if (x.rol === "persona") return typeof x.texto === "string" && typeof x.porVoz === "boolean";
  if (x.rol === "asistente") return esRespuestaAsistente(x.respuesta);
  if (x.rol === "error") return typeof x.texto === "string" && typeof x.pregunta === "string" && typeof x.tipo === "string";
  return false;
}

/** Borra de la pestaña las conversaciones de otras personas (una sesión anterior que no pulsó «Salir»). */
function olvidarOtras(personaId: number) {
  try {
    const propia = claveDe(personaId);
    for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
      const clave = window.sessionStorage.key(i);
      if (clave && clave.startsWith("asistente:v") && clave !== propia) window.sessionStorage.removeItem(clave);
    }
  } catch {
    // Sin almacenamiento no hay nada que borrar.
  }
}

/** Lo guardado en la pestaña, sin entradas dañadas; una pregunta que esperaba ya no tendrá respuesta. */
function leer(personaId: number): Mensaje[] {
  olvidarOtras(personaId);
  try {
    const crudo: unknown = JSON.parse(window.sessionStorage.getItem(claveDe(personaId)) ?? "[]");
    if (!Array.isArray(crudo)) return [];
    return crudo.filter(esMensaje).map((m) => (m.rol === "persona" && m.estado === "esperando" ? { ...m, estado: "perdida" } : m));
  } catch {
    return [];
  }
}

function guardar(personaId: number, mensajes: readonly Mensaje[]) {
  try {
    window.sessionStorage.setItem(claveDe(personaId), JSON.stringify(mensajes.slice(-MAX_MENSAJES)));
  } catch {
    // Sin almacenamiento la conversación dura lo que la página.
  }
}

let secuencia = 0;
const nuevoId = () => `${Date.now().toString(36)}-${(secuencia++).toString(36)}`;

/**
 * Caso de uso «conversar con el asistente». Cada pregunta se responde por separado (el servidor no guarda
 * el hilo); la conversación vive en la pestaña, ligada a la persona, para que siga al cambiar de pantalla.
 */
export function useConversacion() {
  const repositorio = useAsistenteRepository();
  const personaId = usePersonaId();
  // Se lee al montar, en el navegador. Quien usa el asistente lo monta con `key={personaId}`: si cambia la
  // persona en la pestaña, empieza de cero y nunca ve la conversación de otra.
  const [mensajes, setMensajes] = useState<Mensaje[]>(() => leer(personaId));
  const [esperandoDesde, setEsperandoDesde] = useState<number | null>(null);
  const control = useRef<AbortController | null>(null);

  useEffect(() => {
    guardar(personaId, mensajes);
  }, [personaId, mensajes]);

  useEffect(() => () => control.current?.abort(), []);

  const preguntar = useCallback(
    async (texto: string, porVoz = false) => {
      const pregunta = texto.trim();
      if (!pregunta || control.current) return;
      const id = nuevoId();
      const abortar = new AbortController();
      control.current = abortar;
      setEsperandoDesde(Date.now());
      setMensajes((previos) => [...previos, { id, rol: "persona", texto: pregunta, porVoz, estado: "esperando" }]);
      let siguiente: Mensaje;
      try {
        const respuesta = await repositorio.preguntar(pregunta, abortar.signal);
        siguiente = { id: nuevoId(), rol: "asistente", respuesta };
      } catch (causa) {
        if (abortar.signal.aborted) return; // se empezó otra conversación: nada que mostrar
        const error = comoErrorDeAplicacion(causa);
        siguiente = { id: nuevoId(), rol: "error", texto: error.message, tipo: error.tipo, pregunta };
      } finally {
        if (control.current === abortar) {
          control.current = null;
          setEsperandoDesde(null);
        }
      }
      if (abortar.signal.aborted) return; // la respuesta llegó justo al reiniciar: no entra en la conversación nueva
      setMensajes((previos) => [
        ...previos.map((m) => (m.id === id && m.rol === "persona" ? { ...m, estado: "respondida" as const } : m)),
        siguiente,
      ]);
    },
    [repositorio],
  );

  const reiniciar = useCallback(() => {
    control.current?.abort();
    control.current = null;
    setEsperandoDesde(null);
    setMensajes([]);
  }, []);

  const ultima = [...mensajes].reverse().find((m) => m.rol === "asistente");
  return {
    mensajes,
    esperandoDesde,
    preguntar,
    reiniciar,
    cuenta: ultima && ultima.rol === "asistente" ? { usadas: ultima.respuesta.usadas, tope: ultima.respuesta.tope } : null,
  };
}

/** Caso de uso «dictar»: pasa a texto lo grabado. Los errores llegan ya como errores de aplicación. */
export function useTranscribir() {
  const repositorio = useAsistenteRepository();
  return useCallback(
    async (audio: Blob, signal?: AbortSignal) => {
      try {
        return await repositorio.transcribir(audio, signal);
      } catch (causa) {
        if (signal?.aborted) throw causa;
        throw comoErrorDeAplicacion(causa);
      }
    },
    [repositorio],
  );
}
