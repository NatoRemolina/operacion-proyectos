import type { EstadoGasto, GastoDetalle, GastoResumen } from "@/features/gastos/domain/gastos";
import type { ViajeDetalle, ViajeResumen } from "@/features/viajes/domain/viajes";
import type { Dinero } from "@/shared/domain/tipos";
import type { AccionRevision, CamposRevision, DatosRevision } from "./revision";

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

export type AccionViaje = "aprobar" | "rechazar" | "reabrir" | "cerrar";

export interface CambioEstadoViaje {
  readonly accion: AccionViaje;
  /** Obligatorio para rechazar. */
  readonly motivo?: string;
  /** Aprueba con el precio nuevo del vuelo cuando subió más que la tolerancia. */
  readonly confirmarPrecio?: boolean;
}

export interface ResultadoCambioEstado {
  readonly viaje: ViajeDetalle;
  /** Lo que pasó, en lenguaje claro (con el aviso de precio si lo hubo). */
  readonly mensaje: string;
}

export interface AdministracionRepository {
  /** Solo administración; para otro permiso falla con «prohibido». */
  resumen(signal?: AbortSignal): Promise<ResumenAdmin>;
  /** Solo administración y nunca sobre lo propio («autoaprobacion»). */
  cambiarEstadoViaje(id: number, cambio: CambioEstadoViaje): Promise<ResultadoCambioEstado>;
  /**
   * Corrige, aprueba (también con excepción) o rechaza un gasto. Con la `version` que se vio: si otra
   * persona lo cambió entretanto falla con «cambio_ajeno» y no se aplica nada. Nadie revisa lo suyo
   * («prohibido»). Un motivo corto o un dato que las reglas no admiten: «validacion» con el porqué.
   */
  revisarGasto(id: number, revision: RevisionGasto): Promise<GastoDetalle>;
  /** Solo administración: lectura original, soporte, categorías y viajes a los que reasignar. */
  datosRevision(id: number, signal?: AbortSignal): Promise<DatosRevision>;
  /** Dirección de la nota de voz de una justificación, o `null` si esta fuente no la conserva. */
  urlAudioJustificacion(gastoId: number, justificacionId: number): string | null;
}

export interface RevisionGasto {
  readonly version: number;
  readonly accion: AccionRevision;
  /** Obligatorio para rechazar (la persona lo verá) y para aprobar con excepción (queda en la auditoría). */
  readonly motivo?: string;
  /** Solo lo que se corrigió; el resto se conserva. */
  readonly campos?: CamposRevision;
  /** Reasigna el viaje; 0 lo deja sin viaje. Sin el dato, se conserva. */
  readonly viajeId?: number;
}

export const MOTIVO_MINIMO = 5;

/** `null` si el motivo sirve; si no, cómo corregirlo. La misma regla que aplica el servidor. */
export function problemaDeMotivo(texto: string): string | null {
  return texto.trim().length < MOTIVO_MINIMO
    ? `Escribe el motivo con al menos ${MOTIVO_MINIMO} caracteres: la persona lo leerá.`
    : null;
}
