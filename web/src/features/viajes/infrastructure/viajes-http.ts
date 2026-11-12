import { z } from "zod";
import {
  consulta,
  dineroSchema,
  paginaSchema,
  type ClienteHttp,
} from "@/shared/infrastructure/cliente-http";
import type { ViajeResumen, ViajesRepository } from "../domain/viajes";

const fecha = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const viajeResumenSchema = z.object({
  id: z.number().int().positive(),
  codigo: z.string(),
  estado: z.enum(["pendiente_aprobacion", "aprobado", "rechazado", "cerrado"]),
  estado_texto: z.string(),
  en_curso: z.boolean(),
  origen: z.string(),
  destino: z.string(),
  ida: fecha,
  regreso: fecha,
  proyecto: z.object({ id: z.number().int(), nombre: z.string() }).nullable(),
  titular: z.object({ id: z.number().int(), codigo: z.string(), nombre: z.string() }).nullable(),
  presupuesto_usd: dineroSchema,
  gastado_usd: dineroSchema,
  en_revision_usd: dineroSchema,
  ejecucion_pct: z.number().int().nullable(),
  gastos: z.number().int().nonnegative(),
  propio: z.boolean().default(false),
  precio_por_confirmar: z.string().nullable().default(null),
}) satisfies z.ZodType<ViajeResumen>;

const listaSchema = paginaSchema(viajeResumenSchema);

export function crearViajesHttp(cliente: ClienteHttp): ViajesRepository {
  return {
    listar(filtro, signal) {
      const ruta = `/viajes${consulta({
        estado: filtro.estado,
        limite: filtro.limite,
        cursor: filtro.cursor,
      })}`;
      return cliente.get(ruta, listaSchema, { signal });
    },
  };
}
