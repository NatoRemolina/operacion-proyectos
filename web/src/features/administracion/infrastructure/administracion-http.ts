import { z } from "zod";
import { gastoResumenSchema } from "@/features/gastos/infrastructure/gastos-http";
import { viajeResumenSchema } from "@/features/viajes/infrastructure/viajes-http";
import { dineroSchema, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { ActividadGasto, AdministracionRepository, ResumenAdmin } from "../domain/administracion";

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

export function crearAdministracionHttp(cliente: ClienteHttp): AdministracionRepository {
  return {
    resumen(signal) {
      return cliente.get("/resumen", resumenSchema, { signal });
    },
  };
}
