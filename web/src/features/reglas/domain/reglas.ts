/**
 * Reglas y supuestos: lo que ningún buscador entrega (equipaje, programas de hotel, metas, cuentas
 * contables...). Solo administración las ve y las edita; las membresías se muestran en solo lectura.
 * La validación es la del servidor (`app/servicios/reglas.py`): una regla numérica sigue siendo numérica.
 */

export interface Regla {
  readonly id: number;
  readonly ambito: string;
  readonly entidad: string | null;
  readonly tarifa: string | null;
  readonly clave: string;
  readonly valor: string;
  /** El valor es un número: al editarlo debe seguir siéndolo. */
  readonly numerica: boolean;
  readonly nota: string | null;
  /** Una dirección http(s) o la descripción de dónde sale. */
  readonly fuente: string | null;
  readonly confianza: string | null;
  readonly verificado: string | null;
}

export interface GrupoReglas {
  readonly clave: string;
  readonly titulo: string;
  readonly reglas: readonly Regla[];
}

export interface Membresia {
  readonly id: number;
  readonly titular: string;
  readonly de_empresa: boolean;
  readonly programa: string | null;
  readonly entidad: string | null;
  readonly estatus: string | null;
  /** Inventada para la demostración: se rotula «Dato de ejemplo». */
  readonly ejemplo: boolean;
}

export interface CatalogoReglas {
  readonly grupos: readonly GrupoReglas[];
  readonly membresias: readonly Membresia[];
}

export interface ReglasRepository {
  /** Solo administración; para otro permiso falla con «prohibido». */
  catalogoReglas(signal?: AbortSignal): Promise<CatalogoReglas>;
  /** Guarda el valor nuevo. Si no sirve para esa regla falla con «validacion» y el porqué en `campos.valor`. */
  editarRegla(id: number, valor: string): Promise<Regla>;
}

export const VALOR_MAXIMO = 500;

/** Dígitos con, a lo sumo, un separador decimal (punto o coma): la misma regla que el servidor. */
const NUMERO = /^\d+(?:[.,]\d+)?$/;
/** «1,000»: ¿mil, o uno con tres decimales? Se pregunta en vez de adivinar. */
const MILES_AMBIGUOS = /^\d{1,3},\d{3}$/;
export const AMBIGUO = "¿Mil o uno? Escribe 1000 o 1.0";

/** `null` si el valor sirve para la regla; si no, el mismo texto que daría el servidor. */
export function problemaDeValor(regla: Regla, valor: string): string | null {
  const limpio = valor.trim();
  if (limpio.length > VALOR_MAXIMO) return `El valor no puede pasar de ${VALOR_MAXIMO} caracteres.`;
  if (!regla.numerica) return null;
  if (MILES_AMBIGUOS.test(limpio)) return AMBIGUO;
  return NUMERO.test(limpio) ? null : `«${limpio.slice(0, 30)}» no es un número válido para ${regla.clave}. No se guardó.`;
}

/** Lo que se envía: sin espacios en los extremos; en una regla numérica, con punto decimal. */
export function valorParaEnviar(regla: Regla, valor: string): string {
  const limpio = valor.trim();
  return regla.numerica ? limpio.replace(",", ".") : limpio;
}

/** Solo una dirección http(s) se muestra como enlace; lo demás es texto. */
export function esFuenteEnlace(fuente: string | null): boolean {
  return !!fuente && /^https?:\/\//i.test(fuente);
}
