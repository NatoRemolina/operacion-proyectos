import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { AsistenteRepository, RespuestaAsistente } from "../domain/asistente";

/**
 * Asistente en memoria para pruebas y para el modo demostración. Sin `responder` se comporta como la API
 * con alguien que no es de administración: «prohibido» (la cuenta de demostración es de colaboración).
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
  return {
    async preguntar(pregunta, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.responder) throw new ErrorDeAplicacion("prohibido");
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
