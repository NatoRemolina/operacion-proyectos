import { z } from "zod";
import { gastoResumenSchema } from "@/features/gastos/infrastructure/gastos-http";
import { viajeResumenSchema } from "@/features/viajes/infrastructure/viajes-http";
import { consulta, dineroSchema, paginaSchema, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { CategoriaProyecto, ProyectoResumen, ProyectosRepository, TableroProyecto } from "../domain/proyectos";

const fecha = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const proyectoResumenSchema = z.object({
  id: z.number().int().positive(),
  nombre: z.string(),
  cliente: z.string().nullable(),
  ciudad: z.string().nullable(),
  fecha_inicio: fecha,
  fecha_fin: fecha,
  moneda: z.string(),
  viajes: z.number().int().nonnegative(),
  gastos: z.number().int().nonnegative(),
  previsto_usd: dineroSchema,
  real_usd: dineroSchema,
  diferencia_usd: dineroSchema,
}) satisfies z.ZodType<ProyectoResumen>;

const categoriaSchema = z.object({
  clave: z.string(),
  nombre: z.string(),
  previsto_usd: dineroSchema,
  real_usd: dineroSchema,
  diferencia_usd: dineroSchema,
}) satisfies z.ZodType<CategoriaProyecto>;

const tableroSchema = z.object({
  proyecto: proyectoResumenSchema,
  categorias: z.array(categoriaSchema),
  previsto_usd: dineroSchema,
  real_usd: dineroSchema,
  diferencia_usd: dineroSchema,
  en_revision: z.number().int().nonnegative(),
  faltantes: z.array(z.string()),
  viajes: z.array(viajeResumenSchema),
  gastos: z.array(gastoResumenSchema.extend({ viajero: z.string().nullable() })),
  periodo_contable: z.object({ desde: fecha, hasta: fecha }),
}) satisfies z.ZodType<TableroProyecto>;

const listaSchema = paginaSchema(proyectoResumenSchema);

export function crearProyectosHttp(cliente: ClienteHttp): ProyectosRepository {
  return {
    listar(opciones, signal) {
      return cliente.get(`/proyectos${consulta({ limite: opciones.limite, cursor: opciones.cursor })}`, listaSchema, { signal });
    },
    obtener(id, signal) {
      return cliente.get(`/proyectos/${encodeURIComponent(id)}`, tableroSchema, { signal });
    },
    crear(datos) {
      return cliente.postJson("/proyectos", datos, proyectoResumenSchema);
    },
    editar(id, datos) {
      return cliente.postJson(`/proyectos/${encodeURIComponent(id)}`, datos, proyectoResumenSchema);
    },
    urlCsv(id) {
      return cliente.url(`/proyectos/${encodeURIComponent(id)}/exportar.csv`);
    },
    urlLibroContable(id, { desde, hasta }) {
      return cliente.url(`/gastos/contable${consulta({ desde, hasta, proyecto_id: id })}`);
    },
  };
}
