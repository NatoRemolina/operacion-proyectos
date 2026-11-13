import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import type { AsistenteRepository, RespuestaAsistente } from "../domain/asistente";
import { AsistenteFlotante } from "./asistente-flotante";

// La pantalla en la que está la persona: cada prueba la fija en `navegacion.ruta`
const navegacion = vi.hoisted(() => ({ ruta: "/inicio" as string | null }));
vi.mock("next/navigation", () => ({ usePathname: () => navegacion.ruta }));

/*
 * Micrófono simulado: getUserMedia, MediaRecorder, AudioContext (decodificar) y OfflineAudioContext (pasar a
 * 16 kHz). Lo que se prueba es el recorrido de la interfaz: permisos, cancelar, cerrar y la transcripción.
 */
let pistasDetenidas = 0;
let grabadores: GrabadorFalso[] = [];
let darPermiso: ((flujo: MediaStream) => void) | null = null;

class GrabadorFalso {
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor() {
    grabadores.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array(16)]) });
    void this.onstop?.();
  }
}

class ContextoFalso {
  state = "running";
  resume = () => Promise.resolve();
  close = () => {
    this.state = "closed";
    return Promise.resolve();
  };
  decodeAudioData = () => Promise.resolve({ duration: 0.5 });
  createAnalyser = () => ({ fftSize: 0, getByteTimeDomainData: () => {} });
  createMediaStreamSource = () => ({ connect: () => {} });
}

class ContextoSinConexionFalso {
  destination = {};
  createBufferSource = () => ({ buffer: null, connect: () => {}, start: () => {} });
  startRendering = () => Promise.resolve({ getChannelData: () => new Float32Array(8000) });
}

function flujoFalso(): MediaStream {
  return { getTracks: () => [{ stop: () => (pistasDetenidas += 1) }] } as unknown as MediaStream;
}

function microfono(modo: "permite" | "niega" | "espera" = "permite") {
  const getUserMedia = vi.fn(() => {
    if (modo === "niega") return Promise.reject(new DOMException("No", "NotAllowedError"));
    if (modo === "espera") return new Promise<MediaStream>((r) => (darPermiso = r));
    return Promise.resolve(flujoFalso());
  });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  return getUserMedia;
}

function respuesta(texto: string): RespuestaAsistente {
  return { texto, modo: "asesor", modo_texto: "Asesor con herramientas", fuentes: [], herramientas: [], duracion_ms: 900, usadas: 1, tope: 40 };
}

function montar(transcribir: AsistenteRepository["transcribir"] = () => Promise.resolve("¿Cómo van los indicadores?")) {
  const preguntar = vi.fn((p: string) => Promise.resolve(respuesta(`Respuesta a: ${p}`)));
  const repositorio: AsistenteRepository = { preguntar, transcribir: vi.fn(transcribir) };
  renderizarConFuente(<AsistenteFlotante />, { asistente: repositorio, permiso: "admin", personaId: 9 });
  return { preguntar, transcribir: repositorio.transcribir as ReturnType<typeof vi.fn> };
}

async function abrirYDictar(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
  await usuario.click(screen.getByRole("button", { name: "Dictar la pregunta con la voz" }));
}

beforeEach(() => {
  pistasDetenidas = 0;
  grabadores = [];
  darPermiso = null;
  vi.stubGlobal("MediaRecorder", GrabadorFalso);
  vi.stubGlobal("AudioContext", ContextoFalso);
  vi.stubGlobal("OfflineAudioContext", ContextoSinConexionFalso);
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("Dictar al asistente", () => {
  it("graba, transcribe y envía la pregunta marcada como dictada; el micrófono se apaga", async () => {
    microfono();
    const usuario = userEvent.setup();
    const { preguntar, transcribir } = montar();
    await abrirYDictar(usuario);
    expect(await screen.findByText("Escuchando")).toBeInTheDocument();
    expect(screen.getByText("Grabando tu pregunta. Pulsa Listo para enviarla.")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: /Listo/ }));
    expect(await screen.findByText("Respuesta a: ¿Cómo van los indicadores?")).toBeInTheDocument();
    expect(screen.getByText("Dictado por voz")).toBeInTheDocument();
    const audio = transcribir.mock.calls[0]![0] as Blob;
    expect(audio.type).toBe("audio/wav");
    expect(preguntar).toHaveBeenCalledWith("¿Cómo van los indicadores?", expect.objectContaining({ contexto: null }), expect.anything());
    expect(pistasDetenidas).toBe(1);
  });

  it("si el navegador niega el micrófono lo explica y no graba", async () => {
    microfono("niega");
    const usuario = userEvent.setup();
    montar();
    await abrirYDictar(usuario);
    expect(await screen.findByRole("alert")).toHaveTextContent("Permite el micrófono en el navegador");
    expect(grabadores).toHaveLength(0);
  });

  it("cancelar mientras se pide el permiso no deja el micrófono encendido", async () => {
    microfono("espera");
    const usuario = userEvent.setup();
    const { transcribir } = montar();
    await abrirYDictar(usuario);
    expect(screen.getByText("Activando el micrófono…")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Cancelar la grabación" }));
    await act(async () => darPermiso?.(flujoFalso()));
    expect(grabadores).toHaveLength(0);
    expect(pistasDetenidas).toBe(1);
    expect(transcribir).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Tu pregunta para el asistente")).toBeInTheDocument();
  });

  it("cerrar el panel mientras graba apaga el micrófono y no envía nada", async () => {
    microfono();
    const usuario = userEvent.setup();
    const { transcribir, preguntar } = montar();
    await abrirYDictar(usuario);
    expect(await screen.findByText("Escuchando")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Cerrar el asistente" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(pistasDetenidas).toBe(1);
    expect(transcribir).not.toHaveBeenCalled();
    expect(preguntar).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Asistente IA" })).toHaveFocus();
  });

  it("una transcripción vacía pide repetir y el tope del día se explica", async () => {
    microfono();
    const usuario = userEvent.setup();
    const transcribir = vi
      .fn<AsistenteRepository["transcribir"]>()
      .mockResolvedValueOnce("  ")
      .mockRejectedValueOnce(new ErrorDeAplicacion("demasiados_intentos"));
    const { preguntar } = montar(transcribir);
    await abrirYDictar(usuario);
    await usuario.click(await screen.findByRole("button", { name: /Listo/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se entendió el audio");
    await usuario.click(screen.getByRole("button", { name: "Dictar la pregunta con la voz" }));
    await usuario.click(await screen.findByRole("button", { name: /Listo/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Llegaste al tope de dictados de hoy");
    expect(preguntar).not.toHaveBeenCalled();
  });

  it("Escape fuera del asistente no lo cierra", async () => {
    microfono();
    const usuario = userEvent.setup();
    renderizarConFuente(
      <>
        <input aria-label="Campo de la pantalla" />
        <AsistenteFlotante />
      </>,
      { asistente: { preguntar: () => Promise.resolve(respuesta("x")), transcribir: () => Promise.resolve("") }, permiso: "admin" },
    );
    await usuario.click(screen.getByRole("button", { name: "Asistente IA" }));
    await usuario.click(screen.getByLabelText("Campo de la pantalla"));
    await usuario.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Asistente IA" })).toBeInTheDocument();
  });
});
