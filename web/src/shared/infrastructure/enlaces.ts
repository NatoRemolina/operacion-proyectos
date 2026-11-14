import { z } from "zod";
import { esEnlaceExterno, esRutaPropia } from "@/shared/domain/enlaces";

/** Un enlace a otro sitio que no cumple el esquema común no se pinta: queda en null. */
export function enlaceExternoSchema(nombres?: readonly string[]) {
  return z.string().transform((u) => (esEnlaceExterno(u, nombres) ? u : null));
}

/** Una ruta de la API (vendedor, captura, evidencia) que no es propia es una respuesta inesperada, no un enlace. */
export const rutaPropiaSchema = z.string().refine(esRutaPropia, { message: "No es una ruta de esta web" });
