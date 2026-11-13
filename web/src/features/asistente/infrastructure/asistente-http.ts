import { z } from "zod";
import type { ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { AsistenteRepository, FuenteAsistente, RespuestaAsistente } from "../domain/asistente";

const fuenteSchema = z.object({
  tipo: z.string(),
  codigo: z.string(),
  destino: z.object({ tipo: z.enum(["viaje", "gasto", "cotizacion"]), id: z.number().int() }).nullable(),
}) satisfies z.ZodType<FuenteAsistente>;

export const respuestaSchema = z.object({
  texto: z.string(),
  modo: z.enum(["asesor", "modelo", "determinista", "tope"]),
  modo_texto: z.string(),
  fuentes: z.array(fuenteSchema),
  herramientas: z.array(z.string()),
  duracion_ms: z.number().int().nonnegative(),
  usadas: z.number().int().nonnegative(),
  tope: z.number().int().nonnegative(),
}) satisfies z.ZodType<RespuestaAsistente>;

const transcripcionSchema = z.object({ texto: z.string() });

export function crearAsistenteHttp(cliente: ClienteHttp): AsistenteRepository {
  return {
    preguntar(pregunta, signal) {
      return cliente.postJson("/asistente", { pregunta: pregunta.trim() }, respuestaSchema, { signal });
    },
    async transcribir(audio, signal) {
      const formulario = new FormData();
      formulario.append("audio", audio, "pregunta.wav");
      const { texto } = await cliente.postFormulario("/asistente/voz", formulario, transcripcionSchema, { signal });
      return texto;
    },
  };
}
