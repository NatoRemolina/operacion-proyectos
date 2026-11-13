"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MAX_GRABACION_S } from "../domain/asistente";
import { FRECUENCIA_VOZ, codificarWav } from "../domain/audio";

export type EstadoGrabadora = "lista" | "pidiendo" | "grabando" | "procesando";

/** El navegador puede grabar y convertir a WAV (micrófono, MediaRecorder y audio sin conexión). */
export function vozSoportada(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof window.MediaRecorder !== "undefined" &&
    typeof window.OfflineAudioContext !== "undefined"
  );
}

/** Decodifica lo grabado (WebM, MP4 u Ogg según el navegador) y lo deja en WAV mono de 16 kHz. */
async function aWav(grabacion: Blob): Promise<Blob> {
  const contexto = new AudioContext();
  let audio: AudioBuffer;
  try {
    audio = await contexto.decodeAudioData(await grabacion.arrayBuffer());
  } finally {
    void contexto.close();
  }
  const fuera = new OfflineAudioContext(1, Math.max(1, Math.ceil(audio.duration * FRECUENCIA_VOZ)), FRECUENCIA_VOZ);
  const fuente = fuera.createBufferSource();
  fuente.buffer = audio;
  fuente.connect(fuera.destination);
  fuente.start();
  const mezcla = await fuera.startRendering();
  return new Blob([codificarWav(mezcla.getChannelData(0), FRECUENCIA_VOZ)], { type: "audio/wav" });
}

function mensajeDelMicrofono(causa: unknown): string {
  const nombre = causa instanceof DOMException ? causa.name : "";
  if (nombre === "NotAllowedError" || nombre === "SecurityError") {
    return "Permite el micrófono en el navegador para dictar la pregunta.";
  }
  if (nombre === "NotFoundError") return "No encontramos un micrófono en este equipo.";
  return "No se pudo usar el micrófono. Escribe la pregunta.";
}

interface Grabacion {
  grabador: MediaRecorder | null;
  flujo: MediaStream | null;
  contexto: AudioContext | null;
  marco: number;
  reloj: number;
  cancelada: boolean;
  trozos: Blob[];
}

/**
 * Graba una pregunta con el micrófono, muestra el nivel de la voz y entrega un WAV al terminar.
 * Se detiene sola a los `MAX_GRABACION_S` segundos; cancelar descarta lo grabado.
 */
export function useGrabadora(opciones: { alTerminar: (wav: Blob) => void; alFallar: (mensaje: string) => void }) {
  const [estado, setEstado] = useState<EstadoGrabadora>("lista");
  const [segundos, setSegundos] = useState(0);
  const [nivel, setNivel] = useState(0);
  const avisos = useRef(opciones);
  const g = useRef<Grabacion>({ grabador: null, flujo: null, contexto: null, marco: 0, reloj: 0, cancelada: false, trozos: [] });

  useEffect(() => {
    avisos.current = opciones;
  });

  const soltar = useCallback(() => {
    const actual = g.current;
    actual.flujo?.getTracks().forEach((pista) => pista.stop());
    if (actual.contexto && actual.contexto.state !== "closed") void actual.contexto.close();
    cancelAnimationFrame(actual.marco);
    window.clearInterval(actual.reloj);
    actual.flujo = null;
    actual.contexto = null;
  }, []);

  const detener = useCallback(() => {
    const grabador = g.current.grabador;
    if (grabador && grabador.state !== "inactive") grabador.stop();
  }, []);

  const cancelar = useCallback(() => {
    g.current.cancelada = true;
    detener();
  }, [detener]);

  const empezar = useCallback(async () => {
    if (g.current.grabador?.state === "recording") return;
    setEstado("pidiendo");
    let flujo: MediaStream;
    try {
      flujo = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (causa) {
      setEstado("lista");
      avisos.current.alFallar(mensajeDelMicrofono(causa));
      return;
    }
    const actual = g.current;
    actual.flujo = flujo;
    actual.trozos = [];
    actual.cancelada = false;
    const grabador = new MediaRecorder(flujo);
    actual.grabador = grabador;
    grabador.ondataavailable = (evento) => {
      if (evento.data.size > 0) actual.trozos.push(evento.data);
    };
    grabador.onstop = async () => {
      soltar();
      setNivel(0);
      actual.grabador = null;
      if (actual.cancelada || actual.trozos.length === 0) {
        setEstado("lista");
        return;
      }
      setEstado("procesando");
      try {
        const wav = await aWav(new Blob(actual.trozos, { type: grabador.mimeType }));
        setEstado("lista");
        avisos.current.alTerminar(wav);
      } catch {
        setEstado("lista");
        avisos.current.alFallar("No se pudo procesar la grabación. Intenta de nuevo o escribe la pregunta.");
      }
    };

    // Nivel de la voz para las barras: unas 12 veces por segundo, no en cada cuadro.
    try {
      const contexto = new AudioContext();
      const analizador = contexto.createAnalyser();
      analizador.fftSize = 512;
      contexto.createMediaStreamSource(flujo).connect(analizador);
      const muestras = new Uint8Array(analizador.fftSize);
      let ultimo = 0;
      const medir = (ahora: number) => {
        if (ahora - ultimo > 80) {
          ultimo = ahora;
          analizador.getByteTimeDomainData(muestras);
          let suma = 0;
          for (const v of muestras) suma += ((v - 128) / 128) ** 2;
          setNivel(Math.min(1, Math.sqrt(suma / muestras.length) * 5));
        }
        actual.marco = requestAnimationFrame(medir);
      };
      actual.contexto = contexto;
      actual.marco = requestAnimationFrame(medir);
    } catch {
      // Sin medidor se graba igual.
    }

    const inicio = Date.now();
    setSegundos(0);
    actual.reloj = window.setInterval(() => {
      const transcurrido = (Date.now() - inicio) / 1000;
      setSegundos(transcurrido);
      if (transcurrido >= MAX_GRABACION_S) detener();
    }, 250);
    grabador.start(250);
    setEstado("grabando");
  }, [detener, soltar]);

  useEffect(
    () => () => {
      g.current.cancelada = true;
      const grabador = g.current.grabador;
      if (grabador && grabador.state !== "inactive") grabador.stop();
      soltar();
    },
    [soltar],
  );

  return { estado, segundos, nivel, empezar, detener, cancelar };
}
