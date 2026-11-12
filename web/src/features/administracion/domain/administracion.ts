import type { EstadoGasto, GastoResumen } from "@/features/gastos/domain/gastos";
import type { ViajeResumen } from "@/features/viajes/domain/viajes";
import type { Dinero } from "@/shared/domain/tipos";

/** Un gasto reciente con la persona a la que pertenece. */
export interface ActividadGasto {
  readonly gasto_id: number;
  readonly comercio: string | null;
  readonly persona: { readonly id: number; readonly codigo: string; readonly nombre: string } | null;
  readonly viaje: { readonly id: number; readonly codigo: string } | null;
  readonly total: Dinero;
  readonly moneda: string | null;
  readonly total_usd: Dinero;
  readonly estado: EstadoGasto;
  readonly estado_texto: string;
  readonly creado: string;
}

/** Lo que administración ve al entrar: cifras del momento, lo que espera decisión y la actividad reciente. */
export interface ResumenAdmin {
  readonly presupuesto_aprobado_usd: Dinero;
  readonly gastado_usd: Dinero;
  readonly disponible_usd: Dinero;
  readonly en_revision_usd: Dinero;
  readonly ejecucion_pct: number | null;
  readonly viajes_por_aprobar: number;
  readonly gastos_en_revision: number;
  readonly pendientes: readonly ViajeResumen[];
  readonly revision: readonly GastoResumen[];
  readonly actividad: readonly ActividadGasto[];
  /** Cómo se calcula el disponible, en palabras. */
  readonly nota: string;
  readonly datos_demostracion: boolean;
}

export interface AdministracionRepository {
  /** Solo administración; para otro permiso falla con «prohibido». */
  resumen(signal?: AbortSignal): Promise<ResumenAdmin>;
}
