import { z } from "zod";
import type { ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { CatalogoReglas, Regla, ReglasRepository } from "../domain/reglas";

export const reglaSchema = z.object({
  id: z.number().int().positive(),
  ambito: z.string(),
  entidad: z.string().nullable(),
  tarifa: z.string().nullable(),
  clave: z.string(),
  valor: z.string(),
  numerica: z.boolean(),
  nota: z.string().nullable(),
  fuente: z.string().nullable(),
  confianza: z.string().nullable(),
  verificado: z.string().nullable(),
}) satisfies z.ZodType<Regla>;

const catalogoSchema = z.object({
  grupos: z.array(z.object({ clave: z.string(), titulo: z.string(), reglas: z.array(reglaSchema) })),
  membresias: z.array(
    z.object({
      id: z.number().int(),
      titular: z.string(),
      de_empresa: z.boolean(),
      programa: z.string().nullable(),
      entidad: z.string().nullable(),
      estatus: z.string().nullable(),
      ejemplo: z.boolean(),
    }),
  ),
}) satisfies z.ZodType<CatalogoReglas>;

/** Reglas por la API v1. Se compone dentro del adaptador de administración: comparten el cliente y su token. */
export function crearReglasHttp(cliente: ClienteHttp): ReglasRepository {
  return {
    catalogoReglas(signal) {
      return cliente.get("/reglas", catalogoSchema, { signal });
    },
    editarRegla(id, valor) {
      return cliente.postJson(`/reglas/${encodeURIComponent(id)}`, { valor }, reglaSchema);
    },
  };
}
