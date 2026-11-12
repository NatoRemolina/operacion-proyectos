import { z } from "zod";
import {
  consulta,
  dineroSchema,
  paginaSchema,
  type ClienteHttp,
} from "@/shared/infrastructure/cliente-http";
import type { GastoDetalle, GastoResumen, GastosRepository } from "../domain/gastos";

export const gastoResumenSchema = z.object({
  id: z.number().int().positive(),
  viaje: z.object({ id: z.number().int(), codigo: z.string() }).nullable(),
  comercio: z.string().nullable(),
  fecha: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(),
  categoria: z.string().nullable(),
  total: dineroSchema,
  moneda: z.string().nullable(),
  total_usd: dineroSchema,
  estado: z.enum(["procesando", "revision", "aprobado_auto", "aprobado", "rechazado"]),
  estado_texto: z.string(),
  creado: z.string(),
}) satisfies z.ZodType<GastoResumen>;

export const gastoDetalleSchema = gastoResumenSchema.extend({
  subtotal: dineroSchema,
  impuesto: dineroSchema,
  propina: dineroSchema,
  motivos: z.array(z.string()),
  alertas: z.array(z.string()),
  canal: z.string(),
  documento_id: z.number().int().nullable(),
  lectura: z.object({ origen: z.string(), confianza: z.number().nullable() }),
}) satisfies z.ZodType<GastoDetalle>;

const listaSchema = paginaSchema(gastoResumenSchema);

export function crearGastosHttp(cliente: ClienteHttp): GastosRepository {
  return {
    listar(filtro, signal) {
      const ruta = `/gastos${consulta({
        viaje_id: filtro.viajeId,
        estado: filtro.estado,
        limite: filtro.limite,
        cursor: filtro.cursor,
      })}`;
      return cliente.get(ruta, listaSchema, { signal });
    },
    obtener(id, signal) {
      return cliente.get(`/gastos/${encodeURIComponent(id)}`, gastoDetalleSchema, { signal });
    },
    enviar({ archivo, viajeId, claveIdempotencia }, signal) {
      const formulario = new FormData();
      formulario.append("archivo", archivo, archivo.name);
      if (viajeId !== null) formulario.append("viaje_id", String(viajeId));
      return cliente.postFormulario("/gastos", formulario, gastoDetalleSchema, {
        cabeceras: { "Idempotency-Key": claveIdempotencia },
        signal,
      });
    },
    urlOriginal(documentoId) {
      return cliente.url(`/documentos/${encodeURIComponent(documentoId)}/contenido`);
    },
  };
}
