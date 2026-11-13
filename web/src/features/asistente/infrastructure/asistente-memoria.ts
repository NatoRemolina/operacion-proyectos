import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { AsistenteRepository, RespuestaAsistente } from "../domain/asistente";

/** Lo que responde el modo demostración: no hay datos reales que consultar. */
export function respuestaDeDemostracion(usadas: number): RespuestaAsistente {
  return {
    texto:
      "En el modo de demostración el asistente no consulta datos. Con la plataforma real responde con tus viajes, tus gastos y tu presupuesto, y cita de dónde sale cada cifra.",
    modo: "determinista",
    modo_texto: "Sin modelo: consultas directas",
    fuentes: [],
    herramientas: [],
    duracion_ms: 0,
    usadas,
    tope: 40,
  };
}

/**
 * Asistente en memoria para pruebas y para el modo demostración. Sin `responder` contesta como el modo
 * demostración: la API acepta los tres permisos, así que la cuenta de demostración (de colaboración) también.
 */
export function crearAsistenteMemoria(
  opciones: {
    responder?: (pregunta: string) => RespuestaAsistente;
    /** Lo que «se entiende» de cualquier audio; sin valor, la voz no está disponible. */
    transcripcion?: string;
    sesion?: SesionMemoria;
    latenciaMs?: number;
  } = {},
): AsistenteRepository {
  const { sesion, latenciaMs = 0 } = opciones;
  let usadas = 0;
  return {
    async preguntar(pregunta, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.responder) return respuestaDeDemostracion(++usadas);
      return opciones.responder(pregunta);
    },
    async transcribir(_audio, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (opciones.transcripcion === undefined) throw new ErrorDeAplicacion("servidor");
      return opciones.transcripcion;
    },
  };
}
