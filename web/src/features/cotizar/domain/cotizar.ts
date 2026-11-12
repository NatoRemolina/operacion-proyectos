import type { Dinero, FechaISO } from "@/shared/domain/tipos";

/**
 * Cotizar un viaje de grabación: lugares, pedido, comparación por costo total esperado y decisión.
 * Tipos con la forma exacta del contrato (contracts/api-v1.md, sección «Cotizar y decidir»).
 */

// ---------- lugares ----------
export interface AeropuertoSugerido {
  readonly iata: string;
  readonly nombre: string | null;
  readonly municipio: string | null;
  readonly km: number | null;
  readonly horas: number | null;
  readonly grande: boolean;
}

export type OrigenSugerencia = "local" | "google";

export interface LugarSugerido {
  readonly tipo: "lugar" | "aeropuerto" | "pais";
  readonly id: string;
  readonly nombre: string;
  readonly region: string;
  readonly pais: string;
  readonly lat: number | null;
  readonly lon: number | null;
  readonly tambien: string | null;
  readonly aviso: string | null;
  readonly origen: OrigenSugerencia;
  readonly aeropuertos: readonly AeropuertoSugerido[];
}

export interface ReglasCarretera {
  readonly factor: number;
  readonly velocidad_kmh: number;
}

export interface ListaLugares {
  readonly resultados: readonly LugarSugerido[];
  readonly aviso_google: string | null;
  readonly carretera: ReglasCarretera;
}

export interface Lugar {
  readonly nombre: string;
  readonly region: string;
  readonly pais: string;
  readonly lat: number;
  readonly lon: number;
}

// ---------- formulario ----------
export interface FormularioCotizacion {
  readonly proyectos: readonly {
    readonly id: number;
    readonly nombre: string;
    readonly ciudad: string | null;
    readonly inicio: string | null;
    readonly fin: string | null;
  }[];
  readonly viajeros: readonly { readonly id: number; readonly nombre: string; readonly base: string | null; readonly soy_yo: boolean }[];
  readonly viajero_propio_id: number | null;
  readonly elige_viajero: boolean;
  readonly razones: readonly { readonly clave: string; readonly texto: string }[];
  readonly precios_en_vivo: boolean;
}

// ---------- pedido ----------
export interface LadoPedido {
  readonly texto: string;
  readonly aeropuertos: readonly string[];
  readonly lugar: Lugar | null;
}

export interface PedidoCotizacion {
  readonly proyecto_id: number;
  readonly viajero_id: number | null;
  readonly origen: LadoPedido;
  readonly destino: LadoPedido;
  readonly ida: FechaISO;
  readonly regreso: FechaISO;
  readonly hora_limite: string | null;
  readonly ciudad_hotel: string;
  readonly baterias_n: number;
  readonly baterias_wh: number;
  readonly maleta: boolean;
  readonly prob_cambio_pct: number;
  readonly carro_dia_usd: string;
}

export interface DecisionPedida {
  readonly vuelo_id: number;
  readonly hotel_id: number | null;
  readonly motivo: string;
  readonly razones: readonly string[];
}

// ---------- comparación ----------
export type TipoLinea = "precio" | "equipaje" | "riesgo_cambio" | "millas" | "traslado" | "otro";

export interface LineaCosto {
  readonly concepto: string;
  readonly valor_usd: Dinero;
  readonly origen: string;
  readonly tipo: TipoLinea;
}

export interface Desglose {
  readonly precio_usd: Dinero;
  readonly equipaje_usd: Dinero;
  readonly riesgo_cambio_usd: Dinero;
  readonly millas_usd: Dinero;
  readonly traslado_usd: Dinero;
}

export interface OpcionVuelo {
  readonly id: number;
  readonly aerolinea: string;
  readonly numeros: readonly string[];
  readonly desde: string | null;
  readonly hasta: string | null;
  readonly sale: string;
  readonly llega: string;
  readonly escalas: number;
  readonly duracion_min: number | null;
  readonly precio_usd: Dinero;
  readonly tarifa: { readonly nombre: string; readonly permite_cambio: boolean; readonly reales: boolean };
  readonly costo_total_usd: Dinero;
  readonly desglose: Desglose;
  readonly lineas: readonly LineaCosto[];
  readonly avisos: readonly string[];
  readonly descartada: string | null;
  readonly recomendada: boolean;
  readonly mas_barata: boolean;
  readonly origen_dato: string | null;
  readonly esperado_usd: Dinero;
  readonly frente_esperado_pct: number | null;
}

export interface OpcionHotel {
  readonly id: number;
  readonly nombre: string;
  readonly noche_usd: Dinero;
  readonly total_usd: Dinero;
  readonly calificacion: number | null;
  readonly clase: number | null;
  readonly programa: string | null;
  readonly origen_dato: string | null;
  readonly recomendada: boolean;
}

export type EstadoViajeCotizado = "pendiente_aprobacion" | "aprobado" | "rechazado" | "cerrado";

export interface Cotizacion {
  readonly id: number;
  readonly estado: "buscando" | "comparando" | "decidido";
  readonly creado: string;
  readonly solicitado_por: string | null;
  readonly proyecto: { readonly id: number; readonly nombre: string | null } | null;
  readonly viajero: { readonly id: number; readonly nombre: string | null } | null;
  readonly origen: { readonly codigo: string; readonly aeropuertos: readonly string[]; readonly lugar: Lugar | null };
  readonly destino: { readonly codigo: string; readonly aeropuertos: readonly string[]; readonly lugar: Lugar | null };
  readonly ciudad_hotel: string | null;
  readonly ida: FechaISO;
  readonly regreso: FechaISO;
  readonly noches: number;
  readonly hora_limite: string | null;
  readonly baterias_n: number;
  readonly baterias_wh: number;
  readonly maleta: boolean;
  readonly prob_cambio_pct: number;
  readonly carro_usd: Dinero;
  readonly equipo: { readonly nivel: "ok" | "aviso" | "bloqueo"; readonly texto: string };
  readonly origen_dato: string | null;
  readonly aviso: string | null;
  readonly fallos: readonly string[];
  readonly recomendacion: string;
  readonly vuelos: readonly OpcionVuelo[];
  readonly descartados: readonly OpcionVuelo[];
  readonly hoteles: readonly OpcionHotel[];
  readonly recomendada_id: number | null;
  readonly mas_barata_id: number | null;
  readonly decision: {
    readonly id: number;
    readonly vuelo_id: number;
    readonly hotel_id: number | null;
    readonly motivo: string | null;
    readonly razones: readonly string[];
    readonly total_usd: Dinero;
    readonly siguio_recomendacion: boolean;
    readonly creado: string;
  } | null;
  readonly viaje: {
    readonly id: number;
    readonly codigo: string;
    readonly estado: EstadoViajeCotizado;
    readonly estado_texto: string;
  } | null;
  readonly puede_decidir: boolean;
  readonly bloqueo: string | null;
}

export interface CotizarRepository {
  /** Proyectos, quién puede viajar y razones de la decisión, según el permiso de la persona. */
  formulario(signal?: AbortSignal): Promise<FormularioCotizacion>;
  /** Sugerencias para el campo de lugar. Con `conGoogle`, suma las de Google (tiene topes de uso). */
  buscarLugares(texto: string, conGoogle: boolean, signal?: AbortSignal): Promise<ListaLugares>;
  /** Busca vuelos y hoteles y devuelve la comparación lista. Puede tardar unos segundos. */
  cotizar(pedido: PedidoCotizacion): Promise<Cotizacion>;
  obtener(id: number, signal?: AbortSignal): Promise<Cotizacion>;
  /** Guarda la decisión y crea el viaje, pendiente de aprobación. */
  decidir(id: number, decision: DecisionPedida): Promise<Cotizacion>;
}

// ---------- reglas del campo de lugar ----------
export interface AeropuertoElegido {
  readonly iata: string;
  readonly nombre: string | null;
  readonly km: number | null;
  readonly horas: number | null;
  readonly origen: OrigenSugerencia;
}

/** Lo que la persona eligió en un campo de lugar: el lugar (si lo hay) y los aeropuertos que se comparan. */
export interface LadoElegido {
  readonly texto: string;
  readonly lugar: Lugar | null;
  readonly aeropuertos: readonly AeropuertoElegido[];
  /** `true` después de elegir de la lista; escribir de nuevo lo vuelve texto libre. */
  readonly elegido: boolean;
  /** Lo escrito en «Agregar otro aeropuerto» que todavía no se eligió de la lista. */
  readonly agregando?: string;
}

export const LADO_VACIO: LadoElegido = { texto: "", lugar: null, aeropuertos: [], elegido: false };
export const MAXIMO_AEROPUERTOS = 8;

export function nombreVisible(s: LugarSugerido): string {
  if (s.tipo === "aeropuerto") return `${s.nombre} (${s.id})`;
  if (s.tipo === "pais" || s.origen === "google") return s.nombre;
  return [s.nombre, s.region, s.pais].filter(Boolean).join(", ");
}

export function ladoDesdeSugerencia(s: LugarSugerido): LadoElegido {
  const lugar =
    s.tipo === "lugar" && s.lat !== null && s.lon !== null
      ? { nombre: s.nombre, region: s.region, pais: s.pais, lat: s.lat, lon: s.lon }
      : null;
  return {
    texto: nombreVisible(s),
    lugar,
    aeropuertos: s.aeropuertos.slice(0, MAXIMO_AEROPUERTOS).map((a) => ({
      iata: a.iata,
      nombre: a.nombre,
      km: a.km,
      horas: a.horas,
      origen: s.origen,
    })),
    elegido: true,
  };
}

/** Distancia en línea recta (fórmula del haversine), igual que el servidor. */
export function distanciaKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = Math.PI / 180;
  const dLat = (lat2 - lat1) * r;
  const dLon = (lon2 - lon1) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(h, 1)));
}

/** Suma los aeropuertos de una sugerencia que no estén ya; la distancia se mide al lugar elegido, si lo hay. */
export function agregarAeropuertos(
  lado: LadoElegido,
  s: LugarSugerido,
  carretera: ReglasCarretera,
): LadoElegido {
  const nuevos: AeropuertoElegido[] = [];
  for (const a of s.aeropuertos) {
    if (lado.aeropuertos.some((x) => x.iata === a.iata) || nuevos.some((x) => x.iata === a.iata)) continue;
    let km: number | null = null;
    let horas: number | null = null;
    if (lado.lugar && s.tipo === "aeropuerto" && s.lat !== null && s.lon !== null) {
      km = distanciaKm(lado.lugar.lat, lado.lugar.lon, s.lat, s.lon);
      horas = (km * carretera.factor) / carretera.velocidad_kmh;
    }
    nuevos.push({ iata: a.iata, nombre: a.nombre, km, horas, origen: s.origen });
  }
  const aeropuertos = [...lado.aeropuertos, ...nuevos].slice(0, MAXIMO_AEROPUERTOS);
  return { ...lado, aeropuertos, elegido: true, agregando: "" };
}

export function quitarAeropuerto(lado: LadoElegido, iata: string): LadoElegido {
  return { ...lado, aeropuertos: lado.aeropuertos.filter((a) => a.iata !== iata) };
}

export function textoDistancia(a: Pick<AeropuertoElegido, "km" | "horas">): string {
  const partes: string[] = [];
  if (a.km !== null) partes.push(a.km < 1 ? "en el lugar" : `${Math.round(a.km)} km`);
  if (a.horas !== null && a.km !== null && a.km >= 1) {
    partes.push(a.horas < 1 ? "menos de 1 h por carretera" : `unas ${Math.round(a.horas)} h por carretera`);
  }
  return partes.join(", ");
}

// ---------- el borrador del formulario ----------
export interface BorradorCotizacion {
  readonly proyectoId: string;
  readonly viajeroId: string;
  readonly origen: LadoElegido;
  readonly destino: LadoElegido;
  readonly ida: string;
  readonly regreso: string;
  readonly horaLimite: string;
  readonly ciudadHotel: string;
  readonly bateriasN: string;
  readonly bateriasWh: string;
  readonly maleta: boolean;
  readonly probCambio: string;
  readonly carroDia: string;
}

export type CampoCotizacion =
  | "proyectoId"
  | "viajeroId"
  | "origen"
  | "destino"
  | "ida"
  | "regreso"
  | "horaLimite"
  | "bateriasN"
  | "bateriasWh"
  | "probCambio"
  | "carroDia";

export type ErroresBorrador = Partial<Record<CampoCotizacion, string>>;

export const BORRADOR_VACIO: BorradorCotizacion = {
  proyectoId: "",
  viajeroId: "",
  origen: LADO_VACIO,
  destino: LADO_VACIO,
  ida: "",
  regreso: "",
  horaLimite: "",
  ciudadHotel: "",
  bateriasN: "0",
  bateriasWh: "0",
  maleta: false,
  probCambio: "0",
  carroDia: "0",
};

const FECHA = /^\d{4}-\d{2}-\d{2}$/;

function numeroEntre(texto: string, minimo: number, maximo: number, decimales = false): boolean {
  const patron = decimales ? /^\d+(\.\d{1,2})?$/ : /^\d+$/;
  if (!patron.test(texto.trim())) return false;
  const n = Number(texto);
  return n >= minimo && n <= maximo;
}

function problemaDeLado(lado: LadoElegido, cual: "origen" | "destino"): string | null {
  if (!lado.texto.trim()) {
    return cual === "origen"
      ? "Escribe de dónde sale: una ciudad, un pueblo o el código de un aeropuerto."
      : "Escribe a dónde va: una ciudad, un pueblo o el código de un aeropuerto.";
  }
  if (lado.agregando?.trim()) return "Termina de agregar el aeropuerto (elígelo de la lista) o borra ese texto.";
  if (lado.elegido && lado.aeropuertos.length === 0) return "Deja al menos un aeropuerto para comparar o agrega otro.";
  return null;
}

/** Revisión previa en el navegador; el servidor vuelve a validar siempre. */
export function validarBorrador(b: BorradorCotizacion): ErroresBorrador {
  const errores: ErroresBorrador = {};
  if (!b.proyectoId) errores.proyectoId = "Elige el proyecto del viaje.";
  if (!b.viajeroId) errores.viajeroId = "Elige quién viaja.";
  const origen = problemaDeLado(b.origen, "origen");
  if (origen) errores.origen = origen;
  const destino = problemaDeLado(b.destino, "destino");
  if (destino) errores.destino = destino;
  if (!FECHA.test(b.ida)) errores.ida = "Elige la fecha de ida.";
  if (!FECHA.test(b.regreso)) errores.regreso = "Elige la fecha de regreso.";
  else if (FECHA.test(b.ida) && b.regreso <= b.ida) errores.regreso = "El regreso debe ser después de la ida.";
  if (b.horaLimite && !/^([01]\d|2[0-3]):[0-5]\d$/.test(b.horaLimite)) {
    errores.horaLimite = "Escribe la hora como 18:00, o déjala vacía.";
  }
  if (!numeroEntre(b.bateriasN, 0, 50)) errores.bateriasN = "Escribe un número entero entre 0 y 50.";
  if (!numeroEntre(b.bateriasWh, 0, 1000, true)) errores.bateriasWh = "Escribe la capacidad en Wh, entre 0 y 1000.";
  if (!numeroEntre(b.probCambio, 0, 100)) errores.probCambio = "Escribe un porcentaje entre 0 y 100.";
  if (!numeroEntre(b.carroDia, 0, 9999, true)) errores.carroDia = "Escribe el valor por día en USD (0 si no hay carro).";
  return errores;
}

function ladoPedido(lado: LadoElegido): LadoPedido {
  return {
    texto: lado.texto.trim(),
    aeropuertos: lado.elegido ? lado.aeropuertos.map((a) => a.iata) : [],
    lugar: lado.elegido ? lado.lugar : null,
  };
}

/** El cuerpo del pedido. Quien viaja se omite cuando es la propia persona: el servidor lo toma de la sesión. */
export function pedidoDesdeBorrador(b: BorradorCotizacion, viajeroPropioId: number | null): PedidoCotizacion {
  const viajero = Number(b.viajeroId);
  return {
    proyecto_id: Number(b.proyectoId),
    viajero_id: viajero === viajeroPropioId ? null : viajero,
    origen: ladoPedido(b.origen),
    destino: ladoPedido(b.destino),
    ida: b.ida,
    regreso: b.regreso,
    hora_limite: b.horaLimite || null,
    ciudad_hotel: b.ciudadHotel.trim(),
    baterias_n: Number(b.bateriasN),
    baterias_wh: Number(b.bateriasWh),
    maleta: b.maleta,
    prob_cambio_pct: Number(b.probCambio),
    carro_dia_usd: b.carroDia.trim() || "0",
  };
}

/** Los campos del contrato que el servidor puede señalar, en el nombre del formulario. */
export const CAMPO_DEL_SERVIDOR: Readonly<Record<string, CampoCotizacion>> = {
  proyecto_id: "proyectoId",
  viajero_id: "viajeroId",
  origen: "origen",
  destino: "destino",
  ida: "ida",
  regreso: "regreso",
  hora_limite: "horaLimite",
  baterias_n: "bateriasN",
  baterias_wh: "bateriasWh",
  prob_cambio_pct: "probCambio",
  carro_dia_usd: "carroDia",
};

export function erroresDelServidor(campos: Readonly<Record<string, string>>): ErroresBorrador {
  const errores: ErroresBorrador = {};
  for (const [campo, mensaje] of Object.entries(campos)) {
    const propio = CAMPO_DEL_SERVIDOR[campo.split(".")[0] ?? ""];
    if (propio && !errores[propio]) errores[propio] = mensaje;
  }
  return errores;
}

/** Lo que se anuncia mientras se busca: «Buscando vuelos en 3 aeropuertos (MIA → CNY, GJT, SLC)…». */
export function textoBusqueda(pedido: PedidoCotizacion): string {
  const n = Math.max(pedido.origen.aeropuertos.length, pedido.destino.aeropuertos.length);
  const ruta = `${codigosOTexto(pedido.origen)} → ${codigosOTexto(pedido.destino)}`;
  return n > 1 ? `Buscando vuelos en ${n} aeropuertos (${ruta})…` : `Buscando vuelos (${ruta})…`;
}

function codigosOTexto(lado: LadoPedido): string {
  return lado.aeropuertos.length ? lado.aeropuertos.join(", ") : lado.texto;
}

/** El caso con precios guardados: sirve sin conexión en vivo al buscador. */
export const MOAB: Lugar = { nombre: "Moab", region: "Utah", pais: "Estados Unidos", lat: 38.57332, lon: -109.54984 };

export function borradorDeEjemplo(base: BorradorCotizacion): BorradorCotizacion {
  return {
    ...base,
    origen: {
      texto: "Miami International Airport (MIA)",
      lugar: null,
      aeropuertos: [{ iata: "MIA", nombre: "Miami International Airport", km: 0, horas: 0, origen: "local" }],
      elegido: true,
    },
    destino: {
      texto: "Moab, Utah, Estados Unidos",
      lugar: MOAB,
      aeropuertos: [
        { iata: "CNY", nombre: "Canyonlands Regional Airport", km: 26.9, horas: 0.5, origen: "local" },
        { iata: "GJT", nombre: "Grand Junction Regional Airport", km: 107.7, horas: 2, origen: "local" },
        { iata: "SLC", nombre: "Salt Lake City International Airport", km: 322.4, horas: 6, origen: "local" },
      ],
      elegido: true,
    },
    ida: "2026-12-08",
    regreso: "2026-12-11",
    horaLimite: "18:00",
    bateriasN: "4",
    bateriasWh: "77",
    maleta: true,
    probCambio: "25",
    carroDia: "65",
  };
}

// ---------- reglas de la comparación y la decisión ----------
export const MOTIVO_MINIMO = 5;

export function sinDatos(c: Pick<Cotizacion, "vuelos" | "descartados">): boolean {
  return c.vuelos.length === 0 && c.descartados.length === 0;
}

export function requiereMotivo(c: Pick<Cotizacion, "recomendada_id">, vueloId: number | null): boolean {
  return vueloId !== null && vueloId !== c.recomendada_id;
}

/** `null` si se puede guardar; si no, el campo y lo que falta. */
export function problemaDeDecision(
  c: Pick<Cotizacion, "recomendada_id">,
  vueloId: number | null,
  motivo: string,
): { campo: "vuelo" | "motivo"; mensaje: string } | null {
  if (vueloId === null) return { campo: "vuelo", mensaje: "Elige uno de los vuelos para guardar la decisión." };
  if (requiereMotivo(c, vueloId) && motivo.trim().length < MOTIVO_MINIMO) {
    return {
      campo: "motivo",
      mensaje: "Elegiste un vuelo distinto al recomendado: cuenta por qué (5 caracteres o más).",
    };
  }
  return null;
}

/** De dónde salen los precios, en palabras para la persona. */
export function textoOrigenDato(origen: string | null): { texto: string; enVivo: boolean } {
  if (origen === "en vivo") return { texto: "Precios en vivo", enVivo: true };
  if (origen === "guardado") return { texto: "Precios guardados", enVivo: false };
  if (origen === "guardado (otras fechas)") return { texto: "Precios guardados de otras fechas", enVivo: false };
  if (origen === "fallida") return { texto: "El buscador no respondió", enVivo: false };
  return { texto: "Sin precios del buscador", enVivo: false };
}

export const ORIGEN_LINEA: Readonly<Record<string, string>> = {
  buscador: "Buscador",
  regla: "Regla",
  supuesto: "Supuesto",
};

export interface SegmentoCosto {
  readonly tipo: "precio" | "equipaje" | "riesgo_cambio" | "traslado";
  readonly nombre: string;
  readonly valor: Dinero;
  /** Para dibujar la barra; nunca para cuentas de dinero. */
  readonly peso: number;
}

const NOMBRE_SEGMENTO: Record<SegmentoCosto["tipo"], string> = {
  precio: "Precio",
  equipaje: "Equipaje",
  riesgo_cambio: "Riesgo de cambio",
  traslado: "Traslado",
};

/** Las partes del costo que suman, en el orden de la barra. Las millas restan y se muestran aparte. */
export function segmentosCosto(d: Desglose): SegmentoCosto[] {
  const valores: Record<SegmentoCosto["tipo"], Dinero> = {
    precio: d.precio_usd,
    equipaje: d.equipaje_usd,
    riesgo_cambio: d.riesgo_cambio_usd,
    traslado: d.traslado_usd,
  };
  return (Object.keys(valores) as SegmentoCosto["tipo"][])
    .map((tipo) => ({ tipo, nombre: NOMBRE_SEGMENTO[tipo], valor: valores[tipo], peso: Math.max(Number(valores[tipo] ?? 0), 0) }))
    .filter((s) => s.peso > 0);
}

/** "07:35" de "2026-12-08 07:35", y cuántos días después llega. */
export function hora(instante: string): string {
  return instante.slice(11, 16);
}

export function diasDespues(sale: string, llega: string): number {
  const a = Date.parse(`${sale.slice(0, 10)}T00:00:00Z`);
  const b = Date.parse(`${llega.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(a) || Number.isNaN(b) ? 0 : Math.round((b - a) / 86_400_000);
}

export function duracion(minutos: number | null): string {
  if (minutos === null) return "";
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** «Miami → Moab»: el lugar si lo hay, si no los aeropuertos. */
export function tituloRuta(c: Pick<Cotizacion, "origen" | "destino">): string {
  const lado = (l: Cotizacion["origen"]) => l.lugar?.nombre ?? l.aeropuertos.join(" · ");
  return `${lado(c.origen)} → ${lado(c.destino)}`;
}
