import { z } from "zod";
import { consulta, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { ResultadoActualizacion, TramoVuelo, VuelosDelDia, VuelosRepository } from "../domain/vuelos";

const txt = z.string().nullable();

const tramoSchema = z.object({
  id: z.number().int(),
  viaje_id: z.number().int(),
  codigo: z.string(),
  titular: txt,
  sentido: z.string(),
  aerolinea: txt,
  numero: z.string(),
  fecha: z.string(),
  desde: txt,
  hasta: txt,
  sale_programada: txt,
  llega_programada: txt,
  llega_estimada: txt,
  estado: txt,
  estado_texto: z.string(),
  retraso: z.number().int(),
  terminal: txt,
  puerta: txt,
  consultas: z.number().int().nullable(),
  hace_min: z.number().int().nullable(),
  llegar_antes: txt,
  en_destino: txt,
  no_llega: z.boolean(),
  omitida: txt,
  ultima_consulta: txt,
  aviso: z
    .object({ momento: txt.optional(), texto: txt.optional(), enviado: z.boolean().nullable().optional(), error: txt.optional() })
    .nullable(),
  origen: txt,
  origen_texto: txt,
}) satisfies z.ZodType<TramoVuelo>;

export const vuelosSchema = z.object({ fecha: txt, hoy: z.string(), tramos: z.array(tramoSchema) }) satisfies z.ZodType<VuelosDelDia>;

const resultadoSchema = z.object({
  consultado: z.boolean(),
  motivo: txt,
  mensaje: z.string(),
  tramo: tramoSchema.nullable(),
}) satisfies z.ZodType<ResultadoActualizacion>;

export function crearVuelosHttp(cliente: ClienteHttp): VuelosRepository {
  return {
    delDia(fecha, signal) {
      return cliente.get(`/vuelos${consulta({ fecha })}`, vuelosSchema, { signal });
    },
    actualizar(tramoId) {
      return cliente.postJson(`/vuelos/${encodeURIComponent(tramoId)}/actualizar`, {}, resultadoSchema);
    },
  };
}
