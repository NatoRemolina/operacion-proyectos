import { z } from "zod";
import { parametrosDeFiltros } from "@/features/kpis/domain/kpis";
import { consulta, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import { PESTANAS, type MonitoreoRepository, type PestanaMonitoreo } from "../domain/monitoreo";

const pestana = z.enum(PESTANAS);
const celda = z.union([z.object({ texto: z.string(), href: z.string().startsWith("/") }), z.number(), z.string(), z.null()]);

export const pestanaSchema = z.object({
  pestana,
  titulo: z.string(),
  nota: z.string().nullable(),
  pestanas: z.array(z.object({ clave: pestana, titulo: z.string() })),
  filtros: z.object({ proyecto_id: z.number().int().nullable(), desde: z.string().nullable(), hasta: z.string().nullable() }),
  proyectos: z.array(z.object({ id: z.number().int(), nombre: z.string() })),
  cifras: z.array(
    z.object({ etiqueta: z.string(), valor: z.union([z.number(), z.string()]).nullable(), unidad: z.string().nullable(), pie: z.string() }),
  ),
  tablas: z.array(
    z.object({
      titulo: z.string(),
      columnas: z.array(z.object({ texto: z.string(), unidad: z.string().nullable(), fin: z.boolean() })),
      filas: z.array(z.array(celda)),
      vacio: z.string(),
      nota: z.string().nullable(),
      barras: z.boolean(),
    }),
  ),
  exportar: z.array(z.object({ vista: z.string(), texto: z.string() })),
}) satisfies z.ZodType<PestanaMonitoreo>;

export function crearMonitoreoHttp(cliente: ClienteHttp): MonitoreoRepository {
  return {
    pestana(p, filtros, signal) {
      return cliente.get(`/monitoreo${consulta({ pestana: p, ...parametrosDeFiltros(filtros) })}`, pestanaSchema, { signal });
    },
    urlExportar(vista, filtros) {
      return cliente.url(`/monitoreo/exportar.csv${consulta({ vista, ...parametrosDeFiltros(filtros) })}`);
    },
  };
}
