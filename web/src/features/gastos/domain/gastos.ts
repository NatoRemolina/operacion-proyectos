import type { TipoError } from "@/shared/domain/errores";
import type { EstadoVisible } from "@/shared/domain/estados";
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

export type TipoJustificacion = "texto" | "audio";
export type EstadoTranscripcion = "no_aplica" | "pendiente" | "hecha" | "fallida";

/** Para qué fue el gasto, con las palabras de la persona (escritas o transcritas de una nota de voz). */
export interface Justificacion {
  readonly id: number;
  readonly tipo: TipoJustificacion;
  readonly canal: string;
  readonly texto: string | null;
  readonly transcripcion: EstadoTranscripcion;
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
  readonly justificaciones: readonly Justificacion[];
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
  /** Opcional: para qué fue el gasto. Vacía no se envía. */
  readonly justificacion?: string;
}

export interface GastosRepository {
  listar(filtro: FiltroGastos, signal?: AbortSignal): Promise<Pagina<GastoResumen>>;
  obtener(id: number, signal?: AbortSignal): Promise<GastoDetalle>;
  /** Devuelve el estado real tras leer y validar; recibirlo no significa aprobarlo. */
  enviar(envio: EnvioRecibo, signal?: AbortSignal): Promise<GastoDetalle>;
  /** Dirección del archivo original, o `null` si esta fuente no lo conserva. */
  urlOriginal(documentoId: number): string | null;
  /** Añade una justificación escrita. Solo puede hacerlo quien hizo el gasto o quien viaja. */
  justificar(id: number, texto: string, signal?: AbortSignal): Promise<GastoDetalle>;
}

export const JUSTIFICACION_MINIMO = 3;
export const JUSTIFICACION_MAXIMO = 2000;

/** Normaliza los espacios; la misma regla que aplica el servidor. */
export function limpiarJustificacion(texto: string): string {
  return texto.split(/\s+/).filter(Boolean).join(" ").slice(0, JUSTIFICACION_MAXIMO);
}

/** `null` si se puede enviar; si no, el texto que explica qué falta. */
export function problemaDeJustificacion(texto: string): string | null {
  return limpiarJustificacion(texto).length < JUSTIFICACION_MINIMO
    ? "Escribe para qué fue el gasto, aunque sea en pocas palabras."
    : null;
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

/** Cómo se muestra el estado de un gasto: lo aprobado solo y lo aprobado por una persona se ven igual. */
export function estadoVisibleGasto(estado: EstadoGasto): EstadoVisible {
  if (estado === "aprobado_auto" || estado === "aprobado") return "aprobado";
  return estado;
}
