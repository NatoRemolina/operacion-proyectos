import type { FiltrosTablero } from "@/features/kpis/domain/kpis";

/** Monitoreo por pestañas (solo administración). Mismo contrato que `GET /api/v1/monitoreo`. */

export const PESTANAS = ["viajes", "gastos", "busquedas", "modelo", "cupos", "auditoria", "calidad"] as const;
export type Pestana = (typeof PESTANAS)[number];

export function leerPestana(valor: unknown): Pestana {
  return PESTANAS.find((p) => p === valor) ?? "gastos";
}

export interface Enlace {
  readonly texto: string;
  readonly href: string;
}

export type Celda = Enlace | number | string | null;

export interface Cifra {
  readonly etiqueta: string;
  readonly valor: number | string | null;
  readonly unidad: string | null;
  readonly pie: string;
}

export interface Columna {
  readonly texto: string;
  readonly unidad: string | null;
  readonly fin: boolean;
}

export interface TablaMonitoreo {
  readonly titulo: string;
  readonly columnas: readonly Columna[];
  readonly filas: readonly (readonly Celda[])[];
  readonly vacio: string;
  readonly nota: string | null;
  readonly barras: boolean;
}

export interface PestanaMonitoreo {
  readonly pestana: Pestana;
  readonly titulo: string;
  readonly nota: string | null;
  readonly pestanas: readonly { readonly clave: Pestana; readonly titulo: string }[];
  readonly filtros: FiltrosTablero;
  readonly proyectos: readonly { readonly id: number; readonly nombre: string }[];
  readonly cifras: readonly Cifra[];
  readonly tablas: readonly TablaMonitoreo[];
  readonly exportar: readonly { readonly vista: string; readonly texto: string }[];
}

export interface MonitoreoRepository {
  /** Solo administración; para otro permiso falla con «prohibido». */
  pestana(pestana: Pestana, filtros: FiltrosTablero, signal?: AbortSignal): Promise<PestanaMonitoreo>;
  /** Dirección del CSV de una vista con los filtros, o `null` si la fuente de datos no exporta. */
  urlExportar(vista: string, filtros: FiltrosTablero): string | null;
}

export function esEnlace(celda: Celda): celda is Enlace {
  return typeof celda === "object" && celda !== null;
}

/** El mayor valor numérico de la segunda columna, para dibujar las barras en proporción. */
export function maximoDeBarras(tabla: Pick<TablaMonitoreo, "filas">): number {
  return Math.max(0, ...tabla.filas.map((f) => (typeof f[1] === "number" ? f[1] : 0)));
}
