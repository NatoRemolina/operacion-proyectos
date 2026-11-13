import type { Persona } from "@/features/auth/domain/auth";

export interface MiCuenta {
  readonly persona: Persona;
  readonly rol_texto: string;
  readonly telegram: {
    readonly vinculado: boolean;
    readonly usuario: string | null;
    /** El bot está configurado en esta instalación. En producción hoy está apagado. */
    readonly canal_activo: boolean;
  };
}

export interface VinculoTelegram {
  /** Código de un solo uso para escribir en el chat del bot: `/start <codigo>`. */
  readonly codigo: string;
  readonly enlace: string | null;
  readonly minutos: number;
}

export interface CuentaRepository {
  obtener(signal?: AbortSignal): Promise<MiCuenta>;
  /** Exige la actual. Cierra las demás sesiones; la de esta pestaña sigue con un token nuevo. */
  cambiarClave(actual: string, nueva: string): Promise<{ mensaje: string }>;
  vincularTelegram(): Promise<VinculoTelegram>;
  desvincularTelegram(): Promise<MiCuenta>;
}

export const CLAVE_ACTUAL = "La contraseña actual no coincide.";
export const CLAVE_NUEVA = "La nueva contraseña debe tener al menos 10 caracteres y ser distinta.";
export const CLAVES_DISTINTAS = "Las dos contraseñas nuevas no coinciden.";

/** Qué corregir antes de enviar. La actual la comprueba el servidor. */
export function problemasDeClave(actual: string, nueva: string, repetida: string): { nueva?: string; repetida?: string } {
  if (nueva.length < 10 || nueva === actual) return { nueva: CLAVE_NUEVA };
  if (nueva !== repetida) return { repetida: CLAVES_DISTINTAS };
  return {};
}
