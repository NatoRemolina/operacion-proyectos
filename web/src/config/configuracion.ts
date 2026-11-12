/**
 * Configuración validada al arrancar. Una variable mal escrita falla con un mensaje claro
 * en vez de caer en silencio en datos de demostración.
 */

export type FuenteDatos = "http" | "demo";

/** `FUENTE_DATOS` (solo servidor): `http` por defecto; `demo` activa el modo demostración. */
export function leerFuenteDatos(valor: string | undefined): FuenteDatos {
  const limpio = (valor ?? "").trim().toLowerCase();
  if (limpio === "" || limpio === "http") return "http";
  if (limpio === "demo") return "demo";
  throw new Error(`FUENTE_DATOS debe ser «http» o «demo»; se recibió «${valor}».`);
}

/** `NEXT_PUBLIC_API_BASE`: ruta del mismo origen (por defecto /api/v1) o un origen http(s). */
export function leerBaseApi(valor: string | undefined): string {
  const limpio = (valor ?? "").trim();
  if (limpio === "") return "/api/v1";
  if (limpio.startsWith("/") && !limpio.startsWith("//")) return limpio.replace(/\/+$/, "");
  let url: URL;
  try {
    url = new URL(limpio);
  } catch {
    throw new Error(`NEXT_PUBLIC_API_BASE no es una ruta ni una URL válida: «${limpio}».`);
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("NEXT_PUBLIC_API_BASE debe ser http(s) y sin credenciales.");
  }
  return limpio.replace(/\/+$/, "");
}
