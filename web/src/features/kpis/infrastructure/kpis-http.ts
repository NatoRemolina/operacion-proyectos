import { z } from "zod";
import { consulta, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import { parametrosDeFiltros, type FichaPersona, type KpisRepository, type RutasFrecuentes, type TableroKpis } from "../domain/kpis";

const estado = z.enum(["verde", "ambar", "rojo", "sin datos", "fuera de rango"]);
const n = z.number().nullable();
const txt = z.string().nullable();

export const kpiSchema = z.object({
  nombre: z.string(),
  titulo: z.string(),
  unidad: z.string(),
  para_que: z.string(),
  formula: z.string(),
  sentido: z.enum(["mayor", "menor"]),
  meta: z.number(),
  alerta: z.number(),
  responsable: z.string(),
  reto: z.number().int(),
  principal: z.boolean(),
  valor: n,
  estado,
  estado_texto: z.string(),
});

const par = z.object({ etiqueta: txt, valor: n });
const grupo = z.object({ nombre: txt, presupuesto: n, gastado: n, pct: n });

export const tableroSchema = z.object({
  filtros: z.object({ proyecto_id: z.number().int().nullable(), desde: txt, hasta: txt }),
  retos: z.array(z.object({ reto: z.number().int(), nombre: z.string() })),
  proyectos: z.array(z.object({ id: z.number().int(), nombre: z.string() })),
  kpis: z.array(kpiSchema),
  resumen: z.object({
    verde: z.number().int(),
    ambar: z.number().int(),
    rojo: z.number().int(),
    sin_datos: z.number().int(),
    fuera_de_rango: z.number().int(),
  }),
  tendencia: z.object({
    semanas: z.array(z.string()),
    filas: z.array(
      z.object({ nombre: z.string(), titulo: z.string(), unidad: z.string(), puntos: z.array(z.object({ valor: n, estado })) }),
    ),
  }),
  cotizacion: z.object({
    cotizaciones_por_persona: z.array(par),
    cotizaciones_por_ruta: z.array(par),
    consultas_por_origen: z.array(par),
    consultas_por_tipo: z.array(par),
    consultas_por_persona: z.array(par),
    consultas_por_ruta: z.array(par),
    errores_buscador: z.array(z.object({ momento: txt, tipo: txt, error: txt })),
    cupo: z
      .object({ plan: txt.optional(), mensual: n.optional(), usadas: n.optional(), restantes: n.optional() })
      .nullable(),
  }),
  gastos: z.object({
    por_viaje: z.array(
      z.object({
        id: z.number().int(),
        codigo: z.string(),
        titular: txt,
        ruta: txt,
        ida: txt,
        estado: z.string(),
        presupuesto: n,
        gastado: n,
        en_revision: n,
        pct: n,
      }),
    ),
    por_proyecto: z.array(grupo),
    por_categoria: z.array(grupo),
    por_moneda: z.array(z.object({ moneda: txt, gastos: z.number().int(), total: n, total_usd: n })),
    revision_antiguas: z.array(
      z.object({ id: z.number().int(), comercio: txt, persona: txt, total_usd: n, dias: n }),
    ),
    real_total: n,
  }),
  personas: z.array(
    z.object({
      id: z.number().int(),
      codigo: z.string(),
      nombre: z.string(),
      rol: z.string(),
      rol_texto: z.string(),
      activo: z.boolean(),
      cotizaciones: z.number().int(),
      viajes: z.number().int(),
      presupuesto: z.number(),
      gastado: z.number(),
      en_revision: z.number(),
      ejecucion: n,
      gastos: z.number().int(),
      gastos_revision: z.number().int(),
    }),
  ),
  por_cargo: z.array(z.object({ cargo: z.string(), viajes: z.number().int(), gasto_usd: z.number(), en_revision: z.number() })),
}) satisfies z.ZodType<TableroKpis>;

export const fichaSchema = z.object({
  usuario: z.object({
    id: z.number().int(),
    codigo: z.string(),
    nombre: z.string(),
    correo: z.string(),
    rol: z.string(),
    rol_texto: z.string(),
    activo: z.boolean(),
    creado: txt,
    cargo: txt,
    viajero: txt,
    base: txt,
  }),
  totales: z.object({ presupuesto: z.number(), gastado: z.number(), en_revision: z.number() }),
  indicadores: z.array(kpiSchema),
  cotizaciones: z.array(
    z.object({
      id: z.number().int(),
      origen: txt,
      destino: txt,
      ida: txt,
      regreso: txt,
      estado: txt,
      creado: txt,
      proyecto: txt,
      viaje: txt,
    }),
  ),
  viajes: z.array(
    z.object({
      id: z.number().int(),
      codigo: z.string(),
      origen: txt,
      destino: txt,
      ida: txt,
      regreso: txt,
      estado: z.string(),
      estado_texto: z.string(),
      proyecto: txt,
      presupuesto_usd: n,
      gastado: n,
      en_revision: n,
      pct: n,
    }),
  ),
  gastos: z.array(
    z.object({
      id: z.number().int(),
      comercio: txt,
      fecha: txt,
      categoria: txt,
      total: n,
      moneda: txt,
      total_usd: n,
      estado: z.string(),
      creado: txt,
      canal: txt,
      viaje: txt,
    }),
  ),
  evidencias: z.array(
    z.object({ id: z.number().int(), tipo: txt, canal: txt, nombre: txt, creado: txt, viaje: txt }),
  ),
  eventos: z.array(
    z.object({
      momento: z.string(),
      entidad: txt,
      entidad_id: z.number().int().nullable(),
      paso: z.string(),
      detalle: txt,
      fuente: txt,
      quien: txt,
    }),
  ),
  gastos_por_estado: z.array(par),
  gastos_por_canal: z.array(par),
}) satisfies z.ZodType<FichaPersona>;

const errorPrecio = z.object({ filas: z.number().int(), mae: n, mape: n });

export const rutasFrecuentesSchema = z.object({
  dias: z.number().int(),
  rutas: z.array(
    z.object({
      ruta: z.string(),
      origen: z.string(),
      destino: z.string(),
      cotizaciones: z.number().int(),
      viajes: z.number().int(),
      observaciones: z.number().int(),
      por_anticipacion: z.object({ "0-7": n.optional(), "8-21": n.optional(), "22-45": n.optional(), "46+": n.optional() }),
      mediana: n,
      volatilidad: n,
      tendencia: z.object({ cambio_pct: z.number(), sentido: z.enum(["sube", "baja", "estable"]) }).nullable(),
      prima_flexibilidad: z.object({ usd: n, pct: n, pares: z.number().int() }).nullable(),
      aerolinea_agencia: z.object({ aerolinea: n, agencia: n, diferencia_usd: n, pares: z.number().int() }).nullable(),
      senal: z.object({
        valor: z.enum(["por debajo", "dentro", "por encima", "sin datos"]),
        referencia: txt.optional(),
        rango: z.array(n).nullable().optional(),
        precio: n.optional(),
      }),
    }),
  ),
  exactitud: errorPrecio.extend({
    mensaje: txt,
    por_ruta: z.array(errorPrecio.extend({ ruta: z.string() })),
    por_mes: z.array(errorPrecio.extend({ mes: z.string() })),
    contra_pagado: errorPrecio.nullable(),
  }),
  tarifas_vistas: z.number().int(),
  pocos_datos: z.boolean(),
  aviso: z.string(),
}) satisfies z.ZodType<RutasFrecuentes>;

export function crearKpisHttp(cliente: ClienteHttp): KpisRepository {
  return {
    tablero(filtros, signal) {
      return cliente.get(`/kpis${consulta(parametrosDeFiltros(filtros))}`, tableroSchema, { signal });
    },
    ficha(id, signal) {
      return cliente.get(`/kpis/personas/${encodeURIComponent(id)}`, fichaSchema, { signal });
    },
    rutasFrecuentes(signal) {
      return cliente.get("/kpis/rutas-frecuentes", rutasFrecuentesSchema, { signal });
    },
    urlExportar(que, filtros) {
      return cliente.url(`/kpis/exportar.csv${consulta({ que, ...parametrosDeFiltros(filtros) })}`);
    },
  };
}
