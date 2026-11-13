import type { GastoResumen } from "@/features/gastos/domain/gastos";
import type { ViajeAsignable } from "./revision";

/**
 * Buzón de correo simulado: lee los correos (.eml) y las confirmaciones en HTML de ejemplo como si
 * llegaran a un buzón de gastos. No hay ningún correo real detrás: la pantalla lo dice siempre.
 */
export interface MensajeBuzon {
  readonly nombre: string;
  /** `correo`: un .eml; `html`: una confirmación guardada como página. */
  readonly formato: "correo" | "html";
  readonly remitente: string | null;
  readonly asunto: string | null;
}

export interface BuzonSimulado {
  readonly simulado: true;
  /** El texto que dice que es simulado, tal como lo da el servidor. */
  readonly aviso: string;
  readonly mensajes: readonly MensajeBuzon[];
  /** Viajes aprobados o pendientes a los que se pueden cargar los correos. */
  readonly viajes: readonly ViajeAsignable[];
}

export interface LecturaBuzon {
  readonly nombres: readonly string[];
  /** `null`: sin viaje (el gasto queda a nombre de quien lee y en revisión). */
  readonly viajeId: number | null;
}

export interface ResultadoBuzon {
  readonly leidos: readonly GastoResumen[];
  readonly errores: readonly { readonly nombre: string; readonly mensaje: string }[];
}
