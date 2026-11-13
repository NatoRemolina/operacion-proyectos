/** Indicadores con meta y semáforo (solo administración). Mismo contrato que `GET /api/v1/kpis`. */

export type EstadoKpi = "verde" | "ambar" | "rojo" | "sin datos";

export interface FiltrosTablero {
  readonly proyecto_id: number | null;
  readonly desde: string | null;
  readonly hasta: string | null;
}

export const SIN_FILTROS: FiltrosTablero = { proyecto_id: null, desde: null, hasta: null };

export interface Kpi {
  readonly nombre: string;
  readonly titulo: string;
  readonly unidad: string;
  readonly para_que: string;
  readonly formula: string;
  readonly sentido: "mayor" | "menor";
  readonly meta: number;
  readonly alerta: number;
  readonly responsable: string;
  readonly reto: number;
  readonly principal: boolean;
  readonly valor: number | null;
  readonly estado: EstadoKpi;
  readonly estado_texto: string;
}

export interface Par {
  readonly etiqueta: string | null;
  readonly valor: number | null;
}

export interface FilaTendencia {
  readonly nombre: string;
  readonly titulo: string;
  readonly unidad: string;
  readonly puntos: readonly { readonly valor: number | null; readonly estado: EstadoKpi }[];
}

export interface EjecucionViaje {
  readonly id: number;
  readonly codigo: string;
  readonly titular: string | null;
  readonly ruta: string | null;
  readonly ida: string | null;
  readonly estado: string;
  readonly presupuesto: number | null;
  readonly gastado: number | null;
  readonly en_revision: number | null;
  readonly pct: number | null;
}

export interface EjecucionGrupo {
  readonly nombre: string | null;
  readonly presupuesto: number | null;
  readonly gastado: number | null;
  readonly pct: number | null;
}

export interface FilaPersona {
  readonly id: number;
  readonly codigo: string;
  readonly nombre: string;
  readonly rol: string;
  readonly rol_texto: string;
  readonly activo: boolean;
  readonly cotizaciones: number;
  readonly viajes: number;
  readonly presupuesto: number;
  readonly gastado: number;
  readonly en_revision: number;
  readonly ejecucion: number | null;
  readonly gastos: number;
  readonly gastos_revision: number;
}

export interface TableroKpis {
  readonly filtros: FiltrosTablero;
  readonly retos: readonly { readonly reto: number; readonly nombre: string }[];
  readonly proyectos: readonly { readonly id: number; readonly nombre: string }[];
  readonly kpis: readonly Kpi[];
  readonly resumen: { readonly verde: number; readonly ambar: number; readonly rojo: number; readonly sin_datos: number };
  readonly tendencia: { readonly semanas: readonly string[]; readonly filas: readonly FilaTendencia[] };
  readonly cotizacion: {
    readonly cotizaciones_por_persona: readonly Par[];
    readonly cotizaciones_por_ruta: readonly Par[];
    readonly consultas_por_origen: readonly Par[];
    readonly consultas_por_tipo: readonly Par[];
    readonly consultas_por_persona: readonly Par[];
    readonly consultas_por_ruta: readonly Par[];
    readonly errores_buscador: readonly { readonly momento: string | null; readonly tipo: string | null; readonly error: string | null }[];
    readonly cupo: { readonly plan?: string | null; readonly mensual?: number | null; readonly usadas?: number | null; readonly restantes?: number | null } | null;
  };
  readonly gastos: {
    readonly por_viaje: readonly EjecucionViaje[];
    readonly por_proyecto: readonly EjecucionGrupo[];
    readonly por_categoria: readonly EjecucionGrupo[];
    readonly por_moneda: readonly { readonly moneda: string | null; readonly gastos: number; readonly total: number | null; readonly total_usd: number | null }[];
    readonly revision_antiguas: readonly { readonly id: number; readonly comercio: string | null; readonly persona: string | null; readonly total_usd: number | null; readonly dias: number | null }[];
    readonly real_total: number | null;
  };
  readonly personas: readonly FilaPersona[];
  readonly por_cargo: readonly { readonly cargo: string; readonly viajes: number; readonly gasto_usd: number; readonly en_revision: number }[];
}

export interface EventoPersona {
  readonly momento: string;
  readonly entidad: string | null;
  readonly entidad_id: number | null;
  readonly paso: string;
  readonly detalle: string | null;
  readonly fuente: string | null;
  readonly quien: string | null;
}

export interface FichaPersona {
  readonly usuario: {
    readonly id: number;
    readonly codigo: string;
    readonly nombre: string;
    readonly correo: string;
    readonly rol: string;
    readonly rol_texto: string;
    readonly activo: boolean;
    readonly creado: string | null;
    readonly cargo: string | null;
    readonly viajero: string | null;
    readonly base: string | null;
  };
  readonly totales: { readonly presupuesto: number; readonly gastado: number; readonly en_revision: number };
  readonly indicadores: readonly Kpi[];
  readonly cotizaciones: readonly {
    readonly id: number;
    readonly origen: string | null;
    readonly destino: string | null;
    readonly ida: string | null;
    readonly regreso: string | null;
    readonly estado: string | null;
    readonly creado: string | null;
    readonly proyecto: string | null;
    readonly viaje: string | null;
  }[];
  readonly viajes: readonly {
    readonly id: number;
    readonly codigo: string;
    readonly origen: string | null;
    readonly destino: string | null;
    readonly ida: string | null;
    readonly regreso: string | null;
    readonly estado: string;
    readonly estado_texto: string;
    readonly proyecto: string | null;
    readonly presupuesto_usd: number | null;
    readonly gastado: number | null;
    readonly en_revision: number | null;
    readonly pct: number | null;
  }[];
  readonly gastos: readonly {
    readonly id: number;
    readonly comercio: string | null;
    readonly fecha: string | null;
    readonly categoria: string | null;
    readonly total: number | null;
    readonly moneda: string | null;
    readonly total_usd: number | null;
    readonly estado: string;
    readonly creado: string | null;
    readonly canal: string | null;
    readonly viaje: string | null;
  }[];
  readonly evidencias: readonly {
    readonly id: number;
    readonly tipo: string | null;
    readonly canal: string | null;
    readonly nombre: string | null;
    readonly creado: string | null;
    readonly viaje: string | null;
  }[];
  readonly eventos: readonly EventoPersona[];
  readonly gastos_por_estado: readonly Par[];
  readonly gastos_por_canal: readonly Par[];
}

export type ExportableKpis = "kpis" | "consultas" | "personas";

export interface KpisRepository {
  /** Solo administración; para otro permiso falla con «prohibido». */
  tablero(filtros: FiltrosTablero, signal?: AbortSignal): Promise<TableroKpis>;
  /** Todo lo de una persona y su línea de tiempo. «no_encontrado» si no existe. */
  ficha(id: number, signal?: AbortSignal): Promise<FichaPersona>;
  /** Dirección del CSV con los filtros, o `null` si la fuente de datos no exporta (demostración). */
  urlExportar(que: ExportableKpis, filtros: FiltrosTablero): string | null;
}

const ES_FECHA = /^\d{4}-\d{2}-\d{2}$/;

/** Los filtros que llegan en la dirección de la página; lo que no es válido se ignora, como en el servidor. */
export function leerFiltros(parametros: { proyecto?: unknown; desde?: unknown; hasta?: unknown }): FiltrosTablero {
  const proyecto = typeof parametros.proyecto === "string" && /^\d+$/.test(parametros.proyecto) ? Number(parametros.proyecto) : 0;
  const fecha = (v: unknown) => (typeof v === "string" && ES_FECHA.test(v) ? v : null);
  return { proyecto_id: proyecto > 0 ? proyecto : null, desde: fecha(parametros.desde), hasta: fecha(parametros.hasta) };
}

/** Parámetros de consulta de la API: `proyecto_id`, `desde`, `hasta`, solo los que tienen valor. */
export function parametrosDeFiltros(f: FiltrosTablero): Record<string, string | number | null> {
  return { proyecto_id: f.proyecto_id, desde: f.desde, hasta: f.hasta };
}

/** `?a=1&b=2` con los parámetros que tienen valor; vacío si no queda ninguno. */
export function consultaDeDireccion(parametros: Record<string, string | number | null | undefined>): string {
  const busqueda = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor !== null && valor !== undefined && valor !== "") busqueda.set(clave, String(valor));
  }
  const texto = busqueda.toString();
  return texto ? `?${texto}` : "";
}

/** Los filtros como parámetros de la dirección de la página web (`proyecto`, `desde`, `hasta`). */
export function filtrosEnDireccion(f: FiltrosTablero): Record<string, string | number | null> {
  return { proyecto: f.proyecto_id, desde: f.desde, hasta: f.hasta };
}

export function hayFiltros(f: FiltrosTablero): boolean {
  return f.proyecto_id !== null || f.desde !== null || f.hasta !== null;
}

const NUMERO = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });

/** Un valor con su unidad, como lo muestra la pantalla: «72 %», «USD 1.234,50», «8.000 ms», «3,5 h». */
export function formatearValor(valor: number | null, unidad: string): string {
  if (valor === null) return "Sin datos";
  if (unidad === "USD") {
    return new Intl.NumberFormat("es-CO", { style: "currency", currency: "USD", currencyDisplay: "code" })
      .format(valor)
      .replace(/ /g, " ");
  }
  if (unidad === "%") return `${NUMERO.format(valor)} %`;
  return `${NUMERO.format(valor)} ${unidad}`;
}

/** «Meta ≥ 60 % · rojo si < 30 %»: hacia dónde es mejor y desde dónde preocupa. */
export function textoMeta(k: Pick<Kpi, "sentido" | "meta" | "alerta" | "unidad">): string {
  const signo = k.sentido === "mayor" ? "≥" : "≤";
  const contra = k.sentido === "mayor" ? "<" : ">";
  return `Meta ${signo} ${formatearValor(k.meta, k.unidad)} · rojo si ${contra} ${formatearValor(k.alerta, k.unidad)}`;
}

/** El tono visual de cada estado del semáforo; el texto siempre lo acompaña. */
export function tonoDeEstado(estado: EstadoKpi): "exito" | "aviso" | "error" | "neutro" {
  return estado === "verde" ? "exito" : estado === "ambar" ? "aviso" : estado === "rojo" ? "error" : "neutro";
}
