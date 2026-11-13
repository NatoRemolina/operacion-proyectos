import { z } from "zod";
import { gastoDetalleSchema, gastoResumenSchema } from "@/features/gastos/infrastructure/gastos-http";
import { viajeDetalleSchema, viajeResumenSchema } from "@/features/viajes/infrastructure/viajes-http";
import { dineroSchema, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { ActividadGasto, AdministracionRepository, ResumenAdmin } from "../domain/administracion";
import type { BuzonSimulado, ResultadoBuzon } from "../domain/buzon";
import type { DatosRevision } from "../domain/revision";
import { crearReglasHttp } from "@/features/reglas/infrastructure/reglas-http";

const referencia = z.object({ id: z.number().int(), codigo: z.string() });

const actividadSchema = z.object({
  gasto_id: z.number().int().positive(),
  comercio: z.string().nullable(),
  persona: referencia.extend({ nombre: z.string() }).nullable(),
  viaje: referencia.nullable(),
  total: dineroSchema,
  moneda: z.string().nullable(),
  total_usd: dineroSchema,
  estado: z.enum(["procesando", "revision", "aprobado_auto", "aprobado", "rechazado"]),
  estado_texto: z.string(),
  creado: z.string(),
}) satisfies z.ZodType<ActividadGasto>;

export const resumenSchema = z.object({
  presupuesto_aprobado_usd: dineroSchema,
  gastado_usd: dineroSchema,
  disponible_usd: dineroSchema,
  en_revision_usd: dineroSchema,
  ejecucion_pct: z.number().int().nullable(),
  viajes_por_aprobar: z.number().int().nonnegative(),
  gastos_en_revision: z.number().int().nonnegative(),
  pendientes: z.array(viajeResumenSchema),
  revision: z.array(gastoResumenSchema),
  actividad: z.array(actividadSchema),
  nota: z.string(),
  datos_demostracion: z.boolean(),
}) satisfies z.ZodType<ResumenAdmin>;


export const datosRevisionSchema = z.object({
  gasto_id: z.number().int().positive(),
  version: z.number().int().nonnegative(),
  metodo_pago: z.string().nullable(),
  canal_reserva: z.string().nullable(),
  lectura_original: z
    .object({
      comercio: z.string().nullable(),
      fecha: z.string().nullable(),
      categoria: z.string().nullable(),
      subtotal: dineroSchema,
      impuesto: dineroSchema,
      propina: dineroSchema,
      total: dineroSchema,
      moneda: z.string().nullable(),
      metodo_pago: z.string().nullable(),
      canal_reserva: z.string().nullable(),
      confianza: z.number().nullable(),
      dudas: z.array(z.string()),
    })
    .nullable(),
  soporte: z
    .object({ documento_id: z.number().int(), nombre: z.string().nullable(), forma: z.enum(["imagen", "pdf", "descarga"]) })
    .nullable(),
  categorias: z.array(z.object({ clave: z.string(), nombre: z.string() })),
  viajes: z.array(
    z.object({
      id: z.number().int(),
      codigo: z.string(),
      estado: z.enum(["pendiente_aprobacion", "aprobado", "rechazado", "cerrado"]),
      estado_texto: z.string(),
      titular: z.string().nullable(),
      origen: z.string().nullable(),
      destino: z.string().nullable(),
      ida: z.string().nullable(),
      regreso: z.string().nullable(),
    }),
  ),
  propio: z.boolean(),
  aviso_propio: z.string().nullable(),
}) satisfies z.ZodType<DatosRevision>;

const buzonSchema = z.object({
  simulado: z.literal(true),
  aviso: z.string(),
  mensajes: z.array(
    z.object({ nombre: z.string(), formato: z.enum(["correo", "html"]), remitente: z.string().nullable(), asunto: z.string().nullable() }),
  ),
  viajes: datosRevisionSchema.shape.viajes,
}) satisfies z.ZodType<BuzonSimulado>;

const resultadoBuzonSchema = z.object({
  leidos: z.array(gastoResumenSchema),
  errores: z.array(z.object({ nombre: z.string(), mensaje: z.string() })),
}) satisfies z.ZodType<ResultadoBuzon>;

const resultadoCambioSchema = z.object({ viaje: viajeDetalleSchema, mensaje: z.string() });

export function crearAdministracionHttp(cliente: ClienteHttp): AdministracionRepository {
  return {
    ...crearReglasHttp(cliente),
    resumen(signal) {
      return cliente.get("/resumen", resumenSchema, { signal });
    },
    cambiarEstadoViaje(id, { accion, motivo, confirmarPrecio }) {
      return cliente.postJson(
        `/viajes/${encodeURIComponent(id)}/estado`,
        { accion, motivo: (motivo ?? "").trim(), confirmar_precio: confirmarPrecio ?? false },
        resultadoCambioSchema,
      );
    },
    revisarGasto(id, { version, accion, motivo, campos, viajeId }) {
      return cliente.postJson(
        `/gastos/${encodeURIComponent(id)}/revision`,
        { version, accion, motivo: (motivo ?? "").trim(), ...campos, ...(viajeId === undefined ? {} : { viaje_id: viajeId }) },
        gastoDetalleSchema,
      );
    },
    datosRevision(id, signal) {
      return cliente.get(`/gastos/${encodeURIComponent(id)}/revision`, datosRevisionSchema, { signal });
    },
    buzon(signal) {
      return cliente.get("/buzon", buzonSchema, { signal });
    },
    leerBuzon({ nombres, viajeId }) {
      return cliente.postJson(
        "/buzon/lectura",
        { nombres, ...(viajeId === null ? {} : { viaje_id: viajeId }) },
        resultadoBuzonSchema,
      );
    },
    urlAudioJustificacion(gastoId, justificacionId) {
      return cliente.url(`/gastos/${encodeURIComponent(gastoId)}/justificaciones/${encodeURIComponent(justificacionId)}/audio`);
    },
  };
}
