import { Node } from "constructs";

/** Subdominio de la web nueva si no se indica `-c subdominio=…`. Administración va en `admin.` de este. */
export const SUBDOMINIO_POR_OMISION = "software";

export interface Dominio {
  /** El dominio raíz de la titular de la cuenta. La pila nunca escribe registros en él ni en `www`. */
  raiz: string;
  /** La zona alojada de Route 53, creada a mano por la titular de la cuenta. Se importa: la pila no la crea ni la borra. */
  zonaId: string;
  web: string;
  admin: string;
}

// Una sola etiqueta DNS: así el nombre de la web siempre queda debajo del raíz, nunca en él
const ETIQUETA = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;

function subdominio(nodo: Node): string {
  const valor = nodo.tryGetContext("subdominio");
  const sub = valor === undefined ? SUBDOMINIO_POR_OMISION : String(valor).trim().toLowerCase();
  if (!ETIQUETA.test(sub) || sub === "www") {
    throw new Error(`-c subdominio=${String(valor)} no sirve: debe ser una sola palabra (letras, números o guiones) y no puede ser www, `
      + "que queda para la página personal.");
  }
  return sub;
}

/**
 * Lee `-c dominio=… -c zonaId=…` (y `-c subdominio=…`, por omisión «software»). Sin dominio ni zona, la web se
 * publica en las direcciones gratuitas de CloudFront (ADR 0002). Con uno solo, se detiene: un dominio a medias
 * publicaría en la zona equivocada.
 */
export function dominioDesdeContexto(nodo: Node): Dominio | undefined {
  const raiz = ((nodo.tryGetContext("dominio") as string | undefined) ?? "").trim().replace(/\.$/, "").toLowerCase();
  const zonaId = ((nodo.tryGetContext("zonaId") as string | undefined) ?? "").trim();
  if (!raiz && !zonaId) return undefined;
  if (!zonaId) throw new Error("Falta -c zonaId=…: el identificador de la zona de Route 53 del dominio va junto con -c dominio.");
  if (!raiz) throw new Error("Falta -c dominio=…: el nombre del dominio va junto con -c zonaId.");
  const web = `${subdominio(nodo)}.${raiz}`;
  return { raiz, zonaId, web, admin: `admin.${web}` };
}
