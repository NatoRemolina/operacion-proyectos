import type { GastoDetalle } from "@/features/gastos/domain/gastos";
import type { EstadoViaje } from "@/features/viajes/domain/viajes";
import type { Dinero } from "@/shared/domain/tipos";

/**
 * Revisión completa de un gasto por administración: corregir los datos, reasignar el viaje y decidir.
 * Las reglas (versión esperada, nadie revisa lo suyo, motivos) son las del servidor; aquí solo se
 * prepara lo que se envía y se avisa antes de lo que el servidor rechazaría.
 */

export type AccionRevision = "guardar" | "aprobar" | "excepcion" | "rechazar";

/** Los datos corregidos. Solo viaja lo que cambió; `null` vacía el dato. */
export interface CamposRevision {
  readonly comercio?: string | null;
  readonly fecha?: string | null;
  readonly categoria?: string | null;
  readonly subtotal?: Dinero;
  readonly impuesto?: Dinero;
  readonly propina?: Dinero;
  readonly total?: Dinero;
  readonly moneda?: string | null;
  readonly metodo_pago?: string | null;
  readonly canal_reserva?: string | null;
}

/** Lo que leyó el modelo del recibo, intacto: las correcciones no lo cambian. */
export interface LecturaOriginal {
  readonly comercio: string | null;
  readonly fecha: string | null;
  readonly categoria: string | null;
  readonly subtotal: Dinero;
  readonly impuesto: Dinero;
  readonly propina: Dinero;
  readonly total: Dinero;
  readonly moneda: string | null;
  readonly metodo_pago: string | null;
  readonly canal_reserva: string | null;
  readonly confianza: number | null;
  readonly dudas: readonly string[];
}

export interface SoporteRevision {
  readonly documento_id: number;
  readonly nombre: string | null;
  /** `descarga`: un correo (.eml) o una confirmación HTML guardada como texto; no se muestra al lado. */
  readonly forma: "imagen" | "pdf" | "descarga";
}

export interface ViajeAsignable {
  readonly id: number;
  readonly codigo: string;
  readonly estado: EstadoViaje;
  readonly estado_texto: string;
  readonly titular: string | null;
  readonly origen: string | null;
  readonly destino: string | null;
  readonly ida: string | null;
  readonly regreso: string | null;
}

/** Lo que la revisión necesita además de la ficha del gasto. */
export interface DatosRevision {
  readonly gasto_id: number;
  readonly version: number;
  readonly metodo_pago: string | null;
  readonly canal_reserva: string | null;
  readonly lectura_original: LecturaOriginal | null;
  readonly soporte: SoporteRevision | null;
  readonly categorias: readonly { readonly clave: string; readonly nombre: string }[];
  readonly viajes: readonly ViajeAsignable[];
  readonly propio: boolean;
  readonly aviso_propio: string | null;
}

export const MOTIVO_EXCEPCION_MINIMO = 8;

/** `null` si el motivo sirve; si no, cómo corregirlo. La misma regla que aplica el servidor. */
export function problemaDeMotivoExcepcion(texto: string): string | null {
  return texto.trim().length < MOTIVO_EXCEPCION_MINIMO
    ? `Escribe por qué se aprueba con al menos ${MOTIVO_EXCEPCION_MINIMO} caracteres: queda en la auditoría.`
    : null;
}

/** El formulario tal como se escribe: todo texto. `viaje` es el id o "" (sin viaje). */
export interface FormularioRevision {
  readonly comercio: string;
  readonly fecha: string;
  readonly categoria: string;
  readonly moneda: string;
  readonly subtotal: string;
  readonly impuesto: string;
  readonly propina: string;
  readonly total: string;
  readonly metodo_pago: string;
  readonly canal_reserva: string;
  readonly viaje: string;
}

export function formularioInicial(gasto: GastoDetalle, datos: DatosRevision): FormularioRevision {
  return {
    comercio: gasto.comercio ?? "",
    fecha: gasto.fecha ?? "",
    categoria: gasto.categoria ?? "",
    moneda: gasto.moneda ?? "",
    subtotal: gasto.subtotal ?? "",
    impuesto: gasto.impuesto ?? "",
    propina: gasto.propina ?? "",
    total: gasto.total ?? "",
    metodo_pago: datos.metodo_pago ?? "",
    canal_reserva: datos.canal_reserva ?? "",
    viaje: gasto.viaje ? String(gasto.viaje.id) : "",
  };
}

const ERROR_IMPORTE = "Escribe un importe como 54.00.";

/**
 * Acepta 1234.56, 1234,56, 1.234,56 y 1,234.56, como la revisión de administración: el último
 * separador es el decimal y «45.000» son miles. Vacío quita el importe.
 */
export function importeNormalizado(texto: string): { valor: Dinero } | { error: string } {
  let t = texto.replace(/[^0-9.,-]/g, "");
  if (!t) return texto.trim() ? { error: ERROR_IMPORTE } : { valor: null };
  const comas = (t.match(/,/g) ?? []).length;
  const puntos = (t.match(/\./g) ?? []).length;
  if (comas && puntos) {
    const decimal = t.lastIndexOf(",") > t.lastIndexOf(".") ? "," : ".";
    t = t.replaceAll(decimal === "," ? "." : ",", "").replace(decimal, ".");
  } else if (comas + puntos === 1) {
    const separador = comas ? "," : ".";
    const [entero = "", cola = ""] = t.split(separador);
    t = cola.length === 3 && !["", "0", "-"].includes(entero) ? entero + cola : `${entero}.${cola}`;
  } else if (comas + puntos > 1) {
    t = t.replace(/[.,]/g, "");
  }
  const numero = Number(t);
  return Number.isFinite(numero) && /\d/.test(t) ? { valor: numero.toFixed(2) } : { error: ERROR_IMPORTE };
}

const IMPORTES = ["subtotal", "impuesto", "propina", "total"] as const;
const TEXTOS = ["comercio", "fecha", "categoria", "metodo_pago", "canal_reserva"] as const;

export interface CambiosRevision {
  readonly campos: CamposRevision;
  /** Solo si cambió: el viaje nuevo, o 0 para dejarlo sin viaje. */
  readonly viajeId?: number;
  readonly errores: Readonly<Record<string, string>>;
}

/** Lo que cambió frente a lo que se cargó, listo para enviar, y lo que hay que corregir antes. */
export function cambiosDeRevision(formulario: FormularioRevision, inicial: FormularioRevision): CambiosRevision {
  const campos: Record<string, string | null> = {};
  const errores: Record<string, string> = {};
  for (const campo of TEXTOS) {
    const valor = formulario[campo].trim();
    if (valor !== inicial[campo].trim()) campos[campo] = valor || null;
  }
  if (campos.fecha && !/^\d{4}-\d{2}-\d{2}$/.test(campos.fecha)) errores.fecha = "Elige la fecha del recibo.";
  for (const campo of IMPORTES) {
    if (formulario[campo].trim() === inicial[campo].trim()) continue;
    const leido = importeNormalizado(formulario[campo]);
    if ("error" in leido) errores[campo] = leido.error;
    else if (leido.valor !== (inicial[campo].trim() || null)) campos[campo] = leido.valor;
  }
  const moneda = formulario.moneda.trim().toUpperCase();
  if (moneda !== inicial.moneda.trim().toUpperCase()) {
    if (moneda && !/^[A-Z]{3}$/.test(moneda)) errores.moneda = "La moneda son 3 letras, como USD o EUR.";
    else campos.moneda = moneda || null;
  }
  const viajeId = formulario.viaje === inicial.viaje ? undefined : Number(formulario.viaje || 0);
  return viajeId === undefined ? { campos, errores } : { campos, viajeId, errores };
}
