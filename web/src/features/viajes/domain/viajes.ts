import type { EstadoVisible } from "@/shared/domain/estados";
import type { Dinero, FechaISO, OpcionesListado, Pagina } from "@/shared/domain/tipos";

export type EstadoViaje = "pendiente_aprobacion" | "aprobado" | "rechazado" | "cerrado";

export interface ViajeResumen {
  readonly id: number;
  readonly codigo: string;
  readonly estado: EstadoViaje;
  readonly estado_texto: string;
  readonly en_curso: boolean;
  readonly origen: string;
  readonly destino: string;
  readonly ida: FechaISO;
  readonly regreso: FechaISO;
  readonly proyecto: { readonly id: number; readonly nombre: string } | null;
  readonly titular: { readonly id: number; readonly codigo: string; readonly nombre: string } | null;
  readonly presupuesto_usd: Dinero;
  readonly gastado_usd: Dinero;
  readonly en_revision_usd: Dinero;
  readonly ejecucion_pct: number | null;
  readonly gastos: number;
  /** Es de la persona de la sesión (titular o viajero): nadie aprueba lo suyo. */
  readonly propio?: boolean;
  /** Pendiente cuyo precio de vuelo subió más que la tolerancia: «antes … ahora …». */
  readonly precio_por_confirmar?: string | null;
}

export interface FiltroViajes extends OpcionesListado {
  readonly estado?: EstadoViaje;
}

export interface ViajesRepository {
  /** Viajes visibles para la persona con sesión, el más reciente primero. */
  listar(filtro: FiltroViajes, signal?: AbortSignal): Promise<Pagina<ViajeResumen>>;
}

/** Viajes a los que la persona puede asignar un recibo: los suyos y aprobados. */
export function viajesParaRecibo(
  viajes: readonly ViajeResumen[],
  personaId: number,
): ViajeResumen[] {
  return viajes.filter((v) => v.estado === "aprobado" && v.titular?.id === personaId);
}

/** Cómo se muestra el estado de un viaje: uno aprobado que ocurre hoy se ve «en curso». */
export function estadoVisibleViaje(viaje: Pick<ViajeResumen, "estado" | "en_curso">): EstadoVisible {
  if (viaje.estado === "pendiente_aprobacion") return "pendiente";
  if (viaje.estado === "aprobado" && viaje.en_curso) return "en_curso";
  return viaje.estado;
}
