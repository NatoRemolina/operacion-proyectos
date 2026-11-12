import { ErrorDeAplicacion } from "@/shared/domain/errores";
import type { Pagina } from "@/shared/domain/tipos";

/**
 * Piezas comunes de los adaptadores en memoria (pruebas y modo demostración).
 * Imitan el contrato de la API: sesión, paginación por cursor y latencia.
 */

export interface SesionMemoria {
  personaId(): number | null;
  abrir(personaId: number): void;
  cerrar(): void;
}

export function crearSesionMemoria(
  opciones: { inicial?: number | null; almacen?: Pick<Storage, "getItem" | "setItem" | "removeItem"> } = {},
): SesionMemoria {
  const CLAVE = "demo-sesion";
  let actual: number | null = opciones.inicial ?? null;
  try {
    const guardada = opciones.almacen?.getItem(CLAVE);
    if (guardada) actual = Number(guardada);
  } catch {
    // Sin almacenamiento disponible la sesión dura lo que la pestaña.
  }
  return {
    personaId: () => actual,
    abrir(personaId) {
      actual = personaId;
      try {
        opciones.almacen?.setItem(CLAVE, String(personaId));
      } catch {}
    },
    cerrar() {
      actual = null;
      try {
        opciones.almacen?.removeItem(CLAVE);
      } catch {}
    },
  };
}

export function exigirSesion(sesion: SesionMemoria | undefined): void {
  if (sesion && sesion.personaId() === null) throw new ErrorDeAplicacion("sesion_vencida");
}

export function esperar(ms: number, signal?: AbortSignal): Promise<void> {
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolver, rechazar) => {
    const temporizador = setTimeout(resolver, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(temporizador);
      rechazar(new DOMException("Cancelado", "AbortError"));
    });
  });
}

export function paginar<T>(
  items: readonly T[],
  limite = 20,
  cursor: string | null | undefined = null,
): Pagina<T> {
  const desde = cursor ? Number(cursor) : 0;
  const hasta = desde + Math.min(Math.max(limite, 1), 100);
  return {
    items: items.slice(desde, hasta),
    siguiente: hasta < items.length ? String(hasta) : null,
  };
}
