import type { TipoError } from "@/shared/domain/errores";
import type { Dinero, FechaISO, OpcionesListado, Pagina } from "@/shared/domain/tipos";

export type EstadoGasto = "procesando" | "revision" | "aprobado_auto" | "aprobado" | "rechazado";

export interface GastoResumen {
  readonly id: number;
  readonly viaje: { readonly id: number; readonly codigo: string } | null;
  readonly comercio: string | null;
  readonly fecha: FechaISO | null;
  readonly categoria: string | null;
  readonly total: Dinero;
  readonly moneda: string | null;
  readonly total_usd: Dinero;
  readonly estado: EstadoGasto;
  readonly estado_texto: string;
  readonly creado: string;
}

export interface GastoDetalle extends GastoResumen {
  readonly subtotal: Dinero;
  readonly impuesto: Dinero;
  readonly propina: Dinero;
  readonly motivos: readonly string[];
  readonly alertas: readonly string[];
  readonly canal: string;
  readonly documento_id: number | null;
  readonly lectura: { readonly origen: string; readonly confianza: number | null };
}

export interface FiltroGastos extends OpcionesListado {
  readonly viajeId?: number;
  readonly estado?: EstadoGasto;
}

export interface EnvioRecibo {
  readonly archivo: File;
  /** `null` = automático: la plataforma resuelve el viaje de la persona para hoy. */
  readonly viajeId: number | null;
  /** Una por archivo; se repite si se reintenta el mismo envío. */
  readonly claveIdempotencia: string;
}

export interface GastosRepository {
  listar(filtro: FiltroGastos, signal?: AbortSignal): Promise<Pagina<GastoResumen>>;
  obtener(id: number, signal?: AbortSignal): Promise<GastoDetalle>;
  /** Devuelve el estado real tras leer y validar; recibirlo no significa aprobarlo. */
  enviar(envio: EnvioRecibo, signal?: AbortSignal): Promise<GastoDetalle>;
  /** Dirección del archivo original, o `null` si esta fuente no lo conserva. */
  urlOriginal(documentoId: number): string | null;
}

export const TAMANO_MAXIMO_BYTES = 4.5 * 1024 * 1024;

const TIPOS_ADMITIDOS = ["image/jpeg", "image/png", "image/webp", "application/pdf"];

/** Comprobación previa en el navegador; el servidor vuelve a validar siempre. */
export function validarArchivo(archivo: Pick<File, "size" | "type">): TipoError | null {
  if (archivo.size > TAMANO_MAXIMO_BYTES) return "demasiado_grande";
  // Algunos celulares entregan fotos HEIC o sin tipo: se dejan pasar y decide el servidor.
  if (archivo.type && !archivo.type.startsWith("image/") && !TIPOS_ADMITIDOS.includes(archivo.type)) {
    return "tipo_no_admitido";
  }
  return null;
}

export type ResultadoEnvio = "aprobado" | "revision" | "otro";

export function resultadoDeEnvio(estado: EstadoGasto): ResultadoEnvio {
  if (estado === "aprobado_auto" || estado === "aprobado") return "aprobado";
  if (estado === "revision") return "revision";
  return "otro";
}
