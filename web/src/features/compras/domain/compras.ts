import type { Evidencia } from "@/features/cotizar/domain/cotizar";
import type { Dinero } from "@/shared/domain/tipos";

/** La solicitud de compra del tiquete: nace al decidir y la lleva administración (nunca la de su propio viaje). */
export type EstadoCompra = "solicitada" | "en_analisis" | "se_comprara" | "no_se_comprara" | "comprada" | "cancelada";
export type AccionCompra = "en_analisis" | "se_comprara" | "no_se_comprara" | "cancelada";
export type DestinoClic = "google_flights" | "google_hotels" | "vendedor" | "hotel_oficial";

export interface Compra {
  readonly id: number;
  readonly estado: EstadoCompra;
  readonly estado_texto: string;
  /** La versión que se vio: cada cambio la manda; si otra persona cambió la compra, el servidor responde conflicto. */
  readonly version: number;
  readonly viaje: { readonly id: number; readonly codigo: string; readonly estado: string; readonly presupuesto_usd: Dinero };
  readonly solicitud_id: number | null;
  readonly solicitada_por: string | null;
  readonly motivo: string | null;
  readonly vendedor: string | null;
  readonly localizador: string | null;
  readonly precio_pagado_usd: Dinero;
  /** La tarifa que dio el buscador al decidir. */
  readonly precio_cotizado_usd: Dinero;
  readonly anticipacion_dias: number | null;
  readonly creado: string | null;
  readonly decidido: string | null;
  readonly comprada: string | null;
  readonly frente_presupuesto: {
    readonly presupuesto_usd: Dinero;
    readonly cotizado_usd: Dinero;
    readonly diferencia_usd: Dinero;
  } | null;
}

export interface CompraDetalle extends Compra {
  readonly vuelo: {
    readonly opcion_id: number | null;
    readonly numeros: readonly string[];
    readonly aerolinea: string | null;
    readonly sale: string | null;
    readonly llega: string | null;
    readonly precio_usd: Dinero;
    /** Dirección completa del mismo enlace a la página oficial del vendedor que usa «Ver desglose». */
    readonly vendedor_url: string | null;
    readonly fuente_url: string | null;
  } | null;
  readonly clics: readonly {
    readonly destino: DestinoClic;
    readonly dominio: string | null;
    readonly momento: string | null;
    readonly opcion_id: number | null;
    readonly usuario: string | null;
  }[];
  readonly analisis: {
    readonly estado: "pendiente" | "listo" | "fallido" | "no_disponible";
    readonly motivo: string | null;
    readonly leido: string | null;
    readonly captura_url: string | null;
    readonly aviso_precio: string | null;
  } | null;
  /** La evidencia guardada de la decisión (pieza 5): capturas del vuelo y del hotel y el seguimiento de precios. */
  readonly evidencia: Evidencia | null;
}

export interface RegistroCompra {
  readonly localizador: string;
  readonly precio_pagado: string;
  readonly vendedor: string;
}

export interface ComprasRepository {
  lista(signal?: AbortSignal): Promise<readonly Compra[]>;
  detalle(id: number, signal?: AbortSignal): Promise<CompraDetalle>;
  cambiarEstado(id: number, accion: AccionCompra, version: number, motivo: string): Promise<Compra>;
  registrar(id: number, version: number, registro: RegistroCompra): Promise<Compra>;
  /** Pide (o reutiliza) la lectura de la página del vuelo de la compra. */
  analizar(id: number): Promise<CompraDetalle["analisis"]>;
}

// Las mismas reglas que el servidor (`app/servicios/compras.py`): la pantalla solo ofrece lo que se puede hacer.
const DESDE: Readonly<Record<AccionCompra, readonly EstadoCompra[]>> = {
  en_analisis: ["solicitada"],
  se_comprara: ["solicitada", "en_analisis"],
  no_se_comprara: ["solicitada", "en_analisis"],
  cancelada: ["se_comprara", "comprada"],
};

export const ETIQUETA_ACCION: Readonly<Record<AccionCompra, string>> = {
  en_analisis: "Pasar a análisis",
  se_comprara: "Se va a comprar",
  no_se_comprara: "No se va a comprar",
  cancelada: "Cancelar",
};

export const MOTIVO_MINIMO = 5;

export function accionesPosibles(c: Pick<Compra, "estado">): AccionCompra[] {
  return (Object.keys(DESDE) as AccionCompra[]).filter((a) => DESDE[a].includes(c.estado));
}

export function requiereMotivo(accion: AccionCompra): boolean {
  return accion === "no_se_comprara" || accion === "cancelada";
}

/** «Se va a comprar» exige el viaje aprobado: si no lo está, la razón para mostrarla junto al botón. */
export function bloqueoSeComprara(c: Pick<Compra, "viaje">): string | null {
  return c.viaje.estado === "aprobado" ? null : `El viaje ${c.viaje.codigo} no tiene el presupuesto aprobado.`;
}

export type CampoRegistro = keyof RegistroCompra;

export function validarRegistro(r: RegistroCompra): Partial<Record<CampoRegistro, string>> {
  const errores: Partial<Record<CampoRegistro, string>> = {};
  if (!/^[A-Za-z0-9]{5,8}$/.test(r.localizador.trim())) errores.localizador = "El localizador son 5 a 8 letras o números.";
  if (!/^\d{1,5}(\.\d{1,2})?$/.test(r.precio_pagado.trim()) || Number(r.precio_pagado) <= 0) {
    errores.precio_pagado = "Escribe el precio pagado en USD, como 461.30.";
  }
  if (!r.vendedor.trim()) errores.vendedor = "Escribe a quién se le compró.";
  return errores;
}

export const DESTINO_CLIC: Readonly<Record<DestinoClic, string>> = {
  google_flights: "Google Flights",
  google_hotels: "Google Hotels",
  vendedor: "Página oficial del vendedor",
  hotel_oficial: "Sitio oficial del hotel",
};
