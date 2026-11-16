/**
 * Esquema común de lo que se pinta en un `href` (B7). Lo que no cumple no se pinta como enlace: un enlace a otro sitio
 * queda en null y una ruta propia mal formada es una respuesta inesperada de la API (ver `shared/infrastructure/enlaces`).
 */

// Espacios, caracteres de control y barras invertidas: el navegador los limpia o los lee como «/» y cambia el destino
const RAROS = /[\s\u0000-\u001f\u007f\\]/;

/** Ruta de esta misma web o de su API: una sola «/» al inicio (con dos, el navegador va a otro sitio). */
export function esRutaPropia(url: string): boolean {
  return url.startsWith("/") && !url.startsWith("//") && !RAROS.test(url);
}

/**
 * Enlace a otro sitio: https (o los protocolos que se indiquen), sin credenciales ni puerto, y con un nombre de la
 * lista si se da una (por ejemplo `["t.me"]` para el vínculo de Telegram).
 */
export function esEnlaceExterno(
  url: string,
  nombres?: readonly string[],
  protocolos: readonly string[] = ["https:"],
): boolean {
  if (!url || RAROS.test(url)) return false;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    return false;
  }
  return protocolos.includes(u.protocol) && !u.username && !u.password && !u.port && (!nombres || nombres.includes(u.hostname));
}
