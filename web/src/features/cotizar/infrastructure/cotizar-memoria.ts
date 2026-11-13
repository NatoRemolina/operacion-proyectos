import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import {
  MOTIVO_MINIMO,
  type Cotizacion,
  type CotizarRepository,
  type FormularioCotizacion,
  type ListaLugares,
  type LugarSugerido,
  type PedidoCotizacion,
} from "../domain/cotizar";

const CARRETERA = { factor: 1.3, velocidad_kmh: 70 };

function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .trim();
}

function coincide(s: LugarSugerido, q: string): boolean {
  return [s.nombre, s.region, s.id, ...s.aeropuertos.map((a) => a.iata)].some((x) =>
    normalizar(x).split(/\s+|,/).some((palabra) => palabra.startsWith(q)) || normalizar(x).startsWith(q),
  );
}

/**
 * Cotizaciones en memoria para pruebas y para el modo demostración. Imita las reglas del contrato:
 * sesión, sugerencias locales y de Google, «sin datos» fuera del caso guardado, motivo obligatorio
 * al apartarse de la recomendada y decisión bloqueada cuando el viaje ya está aprobado.
 */
export function crearCotizarMemoria(opciones: {
  formulario: FormularioCotizacion;
  /** Lo que conocen los datos propios. */
  lugares?: readonly LugarSugerido[];
  /** Lo que solo trae Google (se suma con `conGoogle`). */
  lugaresGoogle?: readonly LugarSugerido[];
  /** Respuestas guardadas: si el pedido coincide en destino y fechas, se devuelve una copia. */
  guardadas?: readonly Cotizacion[];
  /** Cotizaciones que ya existen (se pueden abrir y decidir por su id). */
  existentes?: readonly Cotizacion[];
  sesion?: SesionMemoria;
  latenciaMs?: number;
  latenciaBusquedaMs?: number;
}): CotizarRepository {
  const { formulario, lugares = [], lugaresGoogle = [], guardadas = [], sesion, latenciaMs = 0 } = opciones;
  const latenciaBusqueda = opciones.latenciaBusquedaMs ?? latenciaMs;
  const cotizaciones = new Map<number, Cotizacion>((opciones.existentes ?? []).map((c) => [c.id, c]));
  let siguienteId = 500;
  let siguienteViaje = 90;

  function nombreDe<T extends { id: number; nombre: string }>(lista: readonly T[], id: number | null) {
    return lista.find((x) => x.id === id)?.nombre ?? null;
  }

  function desdePedido(pedido: PedidoCotizacion): Cotizacion {
    const id = siguienteId++;
    const viajeroId = pedido.viajero_id ?? formulario.viajero_propio_id ?? 0;
    const guardada = guardadas.find(
      (g) =>
        g.ida === pedido.ida &&
        g.regreso === pedido.regreso &&
        pedido.destino.aeropuertos.some((a) => g.destino.aeropuertos.includes(a)),
    );
    const lado = (l: PedidoCotizacion["origen"]) => ({
      codigo: l.aeropuertos[0] ?? l.texto.slice(0, 3).toUpperCase(),
      aeropuertos: l.aeropuertos.length ? [...l.aeropuertos].sort() : [l.texto.slice(0, 3).toUpperCase()],
      lugar: l.lugar,
    });
    const base: Cotizacion = guardada ?? {
      id,
      estado: "comparando",
      creado: new Date().toISOString().slice(0, 19) + "Z",
      solicitado_por: null,
      proyecto: null,
      viajero: null,
      origen: lado(pedido.origen),
      destino: lado(pedido.destino),
      ciudad_hotel: pedido.ciudad_hotel || pedido.destino.lugar?.nombre || null,
      ida: pedido.ida,
      regreso: pedido.regreso,
      noches: Math.max(1, Math.round((Date.parse(pedido.regreso) - Date.parse(pedido.ida)) / 86_400_000)),
      hora_limite: pedido.hora_limite,
      baterias_n: pedido.baterias_n,
      baterias_wh: pedido.baterias_wh,
      maleta: pedido.maleta,
      prob_cambio_pct: pedido.prob_cambio_pct,
      carro_usd: "0.00",
      equipo: { nivel: "ok", texto: "Sin baterías de repuesto declaradas." },
      origen_dato: "fallida",
      aviso: null,
      fallos: [],
      recomendacion: "No hay vuelos para comparar.",
      vuelos: [],
      descartados: [],
      hoteles: [],
      hoteles_descartados: [],
      hotel_recomendado_id: null,
      recomendada_id: null,
      mas_barata_id: null,
      decision: null,
      viaje: null,
      puede_decidir: false,
      bloqueo: null,
    };
    return {
      ...base,
      id,
      proyecto: { id: pedido.proyecto_id, nombre: nombreDe(formulario.proyectos, pedido.proyecto_id) },
      viajero: { id: viajeroId, nombre: nombreDe(formulario.viajeros, viajeroId) },
    };
  }

  function obtener(id: number): Cotizacion {
    const c = cotizaciones.get(id);
    if (!c) throw new ErrorDeAplicacion("no_encontrado");
    return c;
  }

  return {
    async formulario(signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      return formulario;
    },
    async buscarLugares(texto, conGoogle, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const q = normalizar(texto);
      if (q.length < 2) return { resultados: [], aviso_google: null, carretera: CARRETERA };
      const propios = lugares.filter((s) => coincide(s, q));
      const deGoogle = conGoogle && q.length >= 3 ? lugaresGoogle.filter((s) => coincide(s, q)) : [];
      const lista: ListaLugares = { resultados: [...propios, ...deGoogle].slice(0, 8), aviso_google: null, carretera: CARRETERA };
      return lista;
    },
    async cotizar(pedido) {
      await esperar(latenciaBusqueda);
      exigirSesion(sesion);
      const c = desdePedido(pedido);
      cotizaciones.set(c.id, c);
      return c;
    },
    async obtener(id, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      return obtener(id);
    },
    async decidir(id, decision) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      const c = obtener(id);
      if (c.bloqueo) throw new ErrorDeAplicacion("conflicto");
      const vuelo = [...c.vuelos, ...c.descartados].find((v) => v.id === decision.vuelo_id);
      if (!vuelo) {
        throw new ErrorDeAplicacion("validacion", { campos: { vuelo_id: "Elige un vuelo para guardar la decisión." } });
      }
      const siguio = vuelo.id === c.recomendada_id;
      if (!siguio && decision.motivo.trim().length < MOTIVO_MINIMO) {
        throw new ErrorDeAplicacion("validacion", {
          campos: { motivo: "Elegiste una opción distinta a la recomendada: cuéntanos por qué." },
        });
      }
      const hotel = c.hoteles.find((h) => h.id === decision.hotel_id) ?? null;
      const total = (Number(vuelo.costo_total_usd ?? 0) + Number(hotel?.total_usd ?? 0)).toFixed(2);
      // El presupuesto no lleva el riesgo de cambio ni las millas (solo sirven para comparar)
      const d = vuelo.desglose;
      const presupuesto = [d.precio_usd, d.equipaje_usd, d.traslado_usd, hotel?.total_usd ?? null, c.carro_usd]
        .reduce((suma, v) => suma + Number(v ?? 0), 0)
        .toFixed(2);
      const viaje = {
        ...(c.viaje ?? {
          id: siguienteViaje,
          codigo: `V-2026-${String(siguienteViaje++).padStart(4, "0")}`,
          estado: "pendiente_aprobacion" as const,
          estado_texto: "Pendiente de aprobación",
        }),
        presupuesto_usd: presupuesto,
      };
      const decidida: Cotizacion = {
        ...c,
        estado: "decidido",
        decision: {
          id: (c.decision?.id ?? 0) + 1,
          vuelo_id: vuelo.id,
          hotel_id: hotel?.id ?? null,
          motivo: decision.motivo.trim() || null,
          razones: [...decision.razones],
          total_usd: total,
          siguio_recomendacion: siguio,
          creado: new Date().toISOString().slice(0, 19) + "Z",
          aviso: null,
        },
        viaje,
      };
      cotizaciones.set(id, decidida);
      return decidida;
    },
  };
}
