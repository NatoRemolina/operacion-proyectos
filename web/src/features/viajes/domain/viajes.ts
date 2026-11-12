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
