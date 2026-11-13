import { z } from "zod";
import { dineroSchema, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { Compra, CompraDetalle, ComprasRepository } from "../domain/compras";

const estado = z.enum(["solicitada", "en_analisis", "se_comprara", "no_se_comprara", "comprada", "cancelada"]);

const compraSchema = z.object({
  id: z.number().int(),
  estado,
  estado_texto: z.string(),
  version: z.number().int(),
  viaje: z.object({ id: z.number().int(), codigo: z.string(), estado: z.string(), presupuesto_usd: dineroSchema }),
  solicitud_id: z.number().int().nullable(),
  solicitada_por: z.string().nullable(),
  motivo: z.string().nullable(),
  vendedor: z.string().nullable(),
  localizador: z.string().nullable(),
  precio_pagado_usd: dineroSchema,
  precio_cotizado_usd: dineroSchema,
  anticipacion_dias: z.number().int().nullable(),
  creado: z.string().nullable(),
  decidido: z.string().nullable(),
  comprada: z.string().nullable(),
  frente_presupuesto: z
    .object({ presupuesto_usd: dineroSchema, cotizado_usd: dineroSchema, diferencia_usd: dineroSchema })
    .nullable(),
}) satisfies z.ZodType<Compra>;

const analisisSchema = z
  .object({
    estado: z.enum(["pendiente", "listo", "fallido", "no_disponible"]),
    motivo: z.string().nullable(),
    leido: z.string().nullable(),
    captura_url: z.string().nullable(),
    aviso_precio: z.string().nullable(),
  })
  .nullable();

const detalleSchema = compraSchema.extend({
  vuelo: z
    .object({
      opcion_id: z.number().int().nullable(),
      numeros: z.array(z.string()),
      aerolinea: z.string().nullable(),
      sale: z.string().nullable(),
      llega: z.string().nullable(),
      precio_usd: dineroSchema,
      vendedor_url: z.string().nullable(),
      fuente_url: z.string().nullable(),
    })
    .nullable(),
  clics: z.array(
    z.object({
      destino: z.enum(["google_flights", "google_hotels", "vendedor", "hotel_oficial"]),
      dominio: z.string().nullable(),
      momento: z.string().nullable(),
      opcion_id: z.number().int().nullable(),
      usuario: z.string().nullable(),
    }),
  ),
  analisis: analisisSchema,
}) satisfies z.ZodType<CompraDetalle>;

export function crearComprasHttp(cliente: ClienteHttp): ComprasRepository {
  // Las rutas que da la API llevan su prefijo; la web las abre contra la misma base que el resto
  const absoluta = (ruta: string | null) => (ruta ? cliente.url(ruta.replace(/^\/api\/v1(?=\/)/, "")) : null);
  return {
    async lista(signal) {
      return (await cliente.get("/compras", z.object({ items: z.array(compraSchema) }), { signal })).items;
    },
    async detalle(id, signal) {
      const d = await cliente.get(`/compras/${id}`, detalleSchema, { signal });
      return {
        ...d,
        vuelo: d.vuelo ? { ...d.vuelo, vendedor_url: absoluta(d.vuelo.vendedor_url) } : null,
        analisis: d.analisis ? { ...d.analisis, captura_url: absoluta(d.analisis.captura_url) } : null,
      };
    },
    cambiarEstado(id, accion, version, motivo) {
      return cliente.postJson(`/compras/${id}/estado`, { accion, version, motivo }, compraSchema);
    },
    registrar(id, version, registro) {
      return cliente.postJson(`/compras/${id}/registro`, { version, ...registro }, compraSchema);
    },
    async analizar(id) {
      const a = await cliente.postJson(`/compras/${id}/analisis`, {}, analisisSchema);
      return a ? { ...a, captura_url: absoluta(a.captura_url) } : null;
    },
  };
}
