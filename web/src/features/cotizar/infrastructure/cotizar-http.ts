import { z } from "zod";
import { consulta, dineroSchema, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type {
  Cotizacion,
  CotizarRepository,
  FormularioCotizacion,
  ListaLugares,
} from "../domain/cotizar";

const lugarSchema = z.object({
  nombre: z.string(),
  region: z.string(),
  pais: z.string(),
  lat: z.number(),
  lon: z.number(),
});

const listaLugaresSchema = z.object({
  resultados: z.array(
    z.object({
      tipo: z.enum(["lugar", "aeropuerto", "pais"]),
      id: z.string(),
      nombre: z.string(),
      region: z.string(),
      pais: z.string(),
      lat: z.number().nullable(),
      lon: z.number().nullable(),
      tambien: z.string().nullable(),
      aviso: z.string().nullable(),
      origen: z.enum(["local", "google"]),
      aeropuertos: z.array(
        z.object({
          iata: z.string(),
          nombre: z.string().nullable(),
          municipio: z.string().nullable(),
          km: z.number().nullable(),
          horas: z.number().nullable(),
          grande: z.boolean(),
        }),
      ),
    }),
  ),
  aviso_google: z.string().nullable(),
  carretera: z.object({ factor: z.number(), velocidad_kmh: z.number() }),
}) satisfies z.ZodType<ListaLugares>;

const formularioSchema = z.object({
  proyectos: z.array(
    z.object({
      id: z.number().int(),
      nombre: z.string(),
      ciudad: z.string().nullable(),
      inicio: z.string().nullable(),
      fin: z.string().nullable(),
    }),
  ),
  viajeros: z.array(
    z.object({ id: z.number().int(), nombre: z.string(), base: z.string().nullable(), soy_yo: z.boolean() }),
  ),
  viajero_propio_id: z.number().int().nullable(),
  elige_viajero: z.boolean(),
  razones: z.array(z.object({ clave: z.string(), texto: z.string() })),
  precios_en_vivo: z.boolean(),
}) satisfies z.ZodType<FormularioCotizacion>;

const vueloSchema = z.object({
  id: z.number().int(),
  aerolinea: z.string(),
  numeros: z.array(z.string()),
  desde: z.string().nullable(),
  hasta: z.string().nullable(),
  sale: z.string(),
  llega: z.string(),
  escalas: z.number().int(),
  duracion_min: z.number().int().nullable(),
  precio_usd: dineroSchema,
  tarifa: z.object({ nombre: z.string(), permite_cambio: z.boolean(), reales: z.boolean() }),
  costo_total_usd: dineroSchema,
  desglose: z.object({
    precio_usd: dineroSchema,
    equipaje_usd: dineroSchema,
    riesgo_cambio_usd: dineroSchema,
    millas_usd: dineroSchema,
    traslado_usd: dineroSchema,
  }),
  lineas: z.array(
    z.object({
      concepto: z.string(),
      valor_usd: dineroSchema,
      origen: z.string(),
      tipo: z.enum(["precio", "equipaje", "riesgo_cambio", "millas", "traslado", "otro"]),
    }),
  ),
  avisos: z.array(z.string()),
  descartada: z.string().nullable(),
  recomendada: z.boolean(),
  mas_barata: z.boolean(),
  origen_dato: z.string().nullable(),
  esperado_usd: dineroSchema,
  frente_esperado_pct: z.number().int().nullable(),
});

const ladoSchema = z.object({ codigo: z.string(), aeropuertos: z.array(z.string()), lugar: lugarSchema.nullable() });

export const cotizacionSchema = z.object({
  id: z.number().int().positive(),
  estado: z.enum(["buscando", "comparando", "decidido"]),
  creado: z.string(),
  solicitado_por: z.string().nullable(),
  proyecto: z.object({ id: z.number().int(), nombre: z.string().nullable() }).nullable(),
  viajero: z.object({ id: z.number().int(), nombre: z.string().nullable() }).nullable(),
  origen: ladoSchema,
  destino: ladoSchema,
  ciudad_hotel: z.string().nullable(),
  ida: z.string(),
  regreso: z.string(),
  noches: z.number().int(),
  hora_limite: z.string().nullable(),
  baterias_n: z.number().int(),
  baterias_wh: z.number(),
  maleta: z.boolean(),
  prob_cambio_pct: z.number().int(),
  carro_usd: dineroSchema,
  equipo: z.object({ nivel: z.enum(["ok", "aviso", "bloqueo"]), texto: z.string() }),
  origen_dato: z.string().nullable(),
  aviso: z.string().nullable(),
  fallos: z.array(z.string()),
  recomendacion: z.string(),
  vuelos: z.array(vueloSchema),
  descartados: z.array(vueloSchema),
  hoteles: z.array(
    z.object({
      id: z.number().int(),
      nombre: z.string(),
      noche_usd: dineroSchema,
      total_usd: dineroSchema,
      calificacion: z.number().nullable(),
      clase: z.number().int().nullable(),
      programa: z.string().nullable(),
      origen_dato: z.string().nullable(),
      recomendada: z.boolean(),
    }),
  ),
  recomendada_id: z.number().int().nullable(),
  mas_barata_id: z.number().int().nullable(),
  decision: z
    .object({
      id: z.number().int(),
      vuelo_id: z.number().int(),
      hotel_id: z.number().int().nullable(),
      motivo: z.string().nullable(),
      razones: z.array(z.string()),
      total_usd: dineroSchema,
      siguio_recomendacion: z.boolean(),
      creado: z.string(),
    })
    .nullable(),
  viaje: z
    .object({
      id: z.number().int(),
      codigo: z.string(),
      estado: z.enum(["pendiente_aprobacion", "aprobado", "rechazado", "cerrado"]),
      estado_texto: z.string(),
      presupuesto_usd: dineroSchema,
    })
    .nullable(),
  puede_decidir: z.boolean(),
  bloqueo: z.string().nullable(),
}) satisfies z.ZodType<Cotizacion>;

export function crearCotizarHttp(cliente: ClienteHttp): CotizarRepository {
  return {
    formulario(signal) {
      return cliente.get("/cotizaciones/formulario", formularioSchema, { signal });
    },
    buscarLugares(texto, conGoogle, signal) {
      const ruta = `/lugares${consulta({ q: texto.trim(), google: conGoogle ? 1 : null, limite: 8 })}`;
      return cliente.get(ruta, listaLugaresSchema, { signal });
    },
    cotizar(pedido) {
      // La API admite `Idempotency-Key`; `postJson` del cliente compartido aún no envía cabeceras propias.
      return cliente.postJson("/cotizaciones", pedido, cotizacionSchema);
    },
    obtener(id, signal) {
      return cliente.get(`/cotizaciones/${id}`, cotizacionSchema, { signal });
    },
    decidir(id, decision) {
      return cliente.postJson(`/cotizaciones/${id}/decision`, decision, cotizacionSchema);
    },
  };
}
