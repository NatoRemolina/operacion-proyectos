/**
 * Lo escrito a medias (cotizar, la decisión de una cotización) se guarda en la pestaña con este prefijo: así sobrevive
 * a un error o a la sesión vencida, se borra al enviarlo y se borra entero al cerrar sesión (`olvidarBorradores`).
 */
const PREFIJO = "borrador:";

export function leerBorrador<T>(nombre: string): Partial<T> | null {
  if (typeof window === "undefined") return null;
  try {
    const guardado = window.sessionStorage.getItem(`${PREFIJO}${nombre}`);
    return guardado ? (JSON.parse(guardado) as Partial<T>) : null;
  } catch {
    return null;
  }
}

export function guardarBorrador(nombre: string, valor: unknown): void {
  try {
    window.sessionStorage.setItem(`${PREFIJO}${nombre}`, JSON.stringify(valor));
  } catch {
    // Sin almacenamiento disponible, lo escrito dura lo que la pantalla.
  }
}

export function borrarBorrador(nombre: string): void {
  try {
    window.sessionStorage.removeItem(`${PREFIJO}${nombre}`);
  } catch {
    // Nada que borrar.
  }
}

/** Al cerrar sesión: quien use la pestaña después no ve lo que otra persona dejó a medias. */
export function olvidarBorradores(): void {
  try {
    for (let i = window.sessionStorage.length - 1; i >= 0; i--) {
      const clave = window.sessionStorage.key(i);
      if (clave?.startsWith(PREFIJO)) window.sessionStorage.removeItem(clave);
    }
  } catch {
    // Sin almacenamiento no hay nada que borrar.
  }
}
