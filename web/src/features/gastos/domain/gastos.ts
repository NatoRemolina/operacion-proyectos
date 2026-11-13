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
  /** Es de la persona de la sesión: nadie revisa sus propios gastos. */
  readonly propio?: boolean;
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
  /** Sube con cada cambio; la revisión la manda de vuelta para no pisar el cambio de otra persona. */
  readonly version?: number;
  /** Por qué se rechazó, con las palabras de quien revisó. */
  readonly motivo_rechazo?: string | null;
  /** Hizo el gasto o es quien viaja: puede contar para qué fue. Sin el dato (memoria), se asume que sí. */
  readonly puede_justificar?: boolean;
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
  /** Dirección del Excel contable del periodo (se descarga con la sesión), o `null` si esta fuente no lo genera. */
  urlLibroContable(periodo: PeriodoContable): string | null;
}

/** Periodo del Excel contable, por la fecha del recibo: `AAAA-MM-DD`, los dos días incluidos. */
export interface PeriodoContable {
  readonly desde: string;
  readonly hasta: string;
}

const FECHA = /^\d{4}-\d{2}-\d{2}$/;
const dia = (fecha: Date) =>
  `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}-${String(fecha.getDate()).padStart(2, "0")}`;

/** El mes en curso en la fecha local de quien mira (no en UTC: a las 23:00 en Miami ya es otro día en UTC). */
export function mesEnCurso(hoy: Date = new Date()): PeriodoContable {
  return {
    desde: dia(new Date(hoy.getFullYear(), hoy.getMonth(), 1)),
    hasta: dia(new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0)),
  };
}

/** `null` si el periodo se puede descargar; si no, qué corregir. Las mismas reglas que el servidor. */
export function problemaDePeriodo({ desde, hasta }: PeriodoContable): string | null {
  if (!FECHA.test(desde) || !FECHA.test(hasta)) return "Elige la fecha inicial y la final.";
  return hasta < desde ? "La fecha final no puede ser anterior a la inicial." : null;
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

/** El mismo tope que el servidor: 4,5 MB decimales (4.500.000 bytes), no 4,5 MiB. */
export const TAMANO_MAXIMO_BYTES = 4_500_000;

const TIPOS_ADMITIDOS = ["image/jpeg", "image/png", "image/webp", "application/pdf", "message/rfc822"];

/** Un correo guardado (.eml), como la confirmación de una reserva. El navegador no siempre le pone tipo. */
export function esCorreo(archivo: Pick<File, "type" | "name">): boolean {
  return archivo.type === "message/rfc822" || archivo.name.toLowerCase().endsWith(".eml");
}

/** Comprobación previa en el navegador; el servidor vuelve a validar siempre, mirando el contenido. */
export function validarArchivo(archivo: Pick<File, "size" | "type" | "name">): TipoError | null {
  if (archivo.size > TAMANO_MAXIMO_BYTES) return "demasiado_grande";
  // Algunos celulares entregan fotos HEIC o sin tipo, y un .eml puede llegar con un tipo genérico: decide el servidor.
  if (archivo.type && !archivo.type.startsWith("image/") && !TIPOS_ADMITIDOS.includes(archivo.type) && !esCorreo(archivo)) {
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

/** El siguiente paso de un gasto, en palabras de quien lo mira. */
export function siguientePasoGasto(estado: EstadoGasto, esAdmin: boolean): string {
  switch (estado) {
    case "procesando":
      return "Estamos leyendo el recibo.";
    case "revision":
      return esAdmin ? "Espera tu revisión." : "Administración lo revisa. Si cuentas para qué fue, se resuelve antes.";
    case "rechazado":
      return "Rechazado. Mira el motivo en el detalle.";
    default:
      return "Cuenta en el presupuesto del viaje.";
  }
}
