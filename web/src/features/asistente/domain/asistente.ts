import type { Permiso } from "@/shared/domain/navegacion";

/**
 * Asistente: preguntas en lenguaje natural, por escrito o dictadas, que se responden con cifras de la
 * plataforma y citan de dónde salen. Quién responde lo decide el servidor (asesor, modelo o consultas
 * directas); la interfaz solo muestra cuál fue. Lo que se puede ver también lo decide el servidor, con la
 * sesión: el colaborador ve lo suyo, el gestor además lo de sus proyectos y administración todo.
 */

export type ModoAsistente = "asesor" | "modelo" | "determinista" | "tope";

/** Dónde se ve una fuente en esta web. */
export interface DestinoFuente {
  readonly tipo: "viaje" | "gasto" | "cotizacion";
  readonly id: number;
}

export interface FuenteAsistente {
  /** persona, viaje, gasto, cotizacion, nota o audio. */
  readonly tipo: string;
  /** Cómo la cita la respuesta, por ejemplo «gasto #12». */
  readonly codigo: string;
  /** `null` si no tiene pantalla propia (por ejemplo, una persona). */
  readonly destino: DestinoFuente | null;
}

export interface RespuestaAsistente {
  readonly texto: string;
  readonly modo: ModoAsistente;
  /** El modo en palabras, el mismo que muestra la plataforma. */
  readonly modo_texto: string;
  readonly fuentes: readonly FuenteAsistente[];
  /** Consultas que se hicieron para responder, en orden. */
  readonly herramientas: readonly string[];
  readonly duracion_ms: number;
  /** Preguntas de la persona hoy, incluida esta. */
  readonly usadas: number;
  readonly tope: number;
}

export interface AsistenteRepository {
  /** Para los tres permisos, cada uno con su alcance. Con el asesor puede tardar hasta un minuto. */
  preguntar(pregunta: string, signal?: AbortSignal): Promise<RespuestaAsistente>;
  /** Pasa a texto una pregunta grabada (WAV). Vacío si no se entendió nada. */
  transcribir(audio: Blob, signal?: AbortSignal): Promise<string>;
}

const MODOS: readonly string[] = ["asesor", "modelo", "determinista", "tope"];
const DESTINOS: readonly string[] = ["viaje", "gasto", "cotizacion"];
const esTexto = (x: unknown): x is string => typeof x === "string";
const esNumero = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

/** Una respuesta con la forma completa del contrato (lo guardado en la pestaña puede venir dañado o de otra versión). */
export function esRespuestaAsistente(x: unknown): x is RespuestaAsistente {
  if (!x || typeof x !== "object") return false;
  const r = x as Record<string, unknown>;
  return (
    esTexto(r.texto) &&
    esTexto(r.modo) &&
    MODOS.includes(r.modo) &&
    esTexto(r.modo_texto) &&
    Array.isArray(r.herramientas) &&
    r.herramientas.every(esTexto) &&
    esNumero(r.duracion_ms) &&
    esNumero(r.usadas) &&
    esNumero(r.tope) &&
    Array.isArray(r.fuentes) &&
    r.fuentes.every((f: unknown) => {
      if (!f || typeof f !== "object") return false;
      const fuente = f as Record<string, unknown>;
      if (!esTexto(fuente.tipo) || !esTexto(fuente.codigo)) return false;
      if (fuente.destino === null) return true;
      const d = fuente.destino as Record<string, unknown> | undefined;
      return !!d && esTexto(d.tipo) && DESTINOS.includes(d.tipo) && esNumero(d.id);
    })
  );
}

export const MAX_PREGUNTA = 500;
/** La grabación se detiene sola al llegar aquí: una pregunta, no una reunión. */
export const MAX_GRABACION_S = 60;
/** Desde aquí la espera se explica: el asesor puede estar consultando varias fuentes. */
export const ESPERA_LARGA_S = 20;

const PREGUNTAS_EMPRESA = ["¿Cómo van los indicadores?", "¿Quién mencionó el parqueadero?", "¿Cuál es el gasto real aprobado?"];
const PREGUNTAS_PROPIAS = ["¿Cuánto me queda del presupuesto?", "¿Por qué mi gasto quedó en revisión?", "¿Qué me falta por justificar?"];
const PREGUNTAS_GESTOR = [
  "¿Cómo va el presupuesto de mi proyecto?",
  "¿Qué gastos de mi proyecto están en revisión?",
  "¿Qué me falta por justificar?",
];

/** Las mismas que ofrece la plataforma: administración pregunta por la empresa, el gestor por sus proyectos y el colaborador por lo suyo. */
export function preguntasSugeridas(permiso: Permiso): readonly string[] {
  if (permiso === "admin") return PREGUNTAS_EMPRESA;
  return permiso === "gestor" ? PREGUNTAS_GESTOR : PREGUNTAS_PROPIAS;
}

/** Qué se puede preguntar y qué se puede ver, en palabras de cada permiso. */
export function bienvenidaDe(permiso: Permiso, conVoz = false): string {
  if (permiso === "admin")
    return `Pregunta por viajes, gastos, cotizaciones o indicadores${conVoz ? ", por escrito o con tu voz" : ""}. Cada respuesta cita de dónde salen los datos.`;
  const voz = conVoz ? ", por escrito o con tu voz," : "";
  if (permiso === "gestor")
    return `Pregunta${voz} por tus viajes, tus gastos y tu presupuesto, y por los de los proyectos que gestionas. Solo ves lo tuyo y lo de los proyectos que gestionas.`;
  return `Pregunta${voz} por tus viajes, tus gastos y tu presupuesto: cuánto te queda, por qué un gasto quedó en revisión y qué te falta por justificar. Solo ves lo tuyo.`;
}

export function rutaDeFuente(destino: DestinoFuente | null): string | null {
  if (!destino || !Number.isInteger(destino.id) || destino.id < 1) return null;
  const id = encodeURIComponent(destino.id);
  if (destino.tipo === "gasto") return `/gastos/${id}`;
  if (destino.tipo === "viaje") return `/viajes/${id}`;
  return `/cotizar/${id}`;
}

/** La respuesta la dio un modelo de IA (no las consultas directas ni el aviso del tope). */
export function esDeIa(modo: ModoAsistente): boolean {
  return modo === "asesor" || modo === "modelo";
}

export function duracionLegible(ms: number): string {
  return `${(ms / 1000).toLocaleString("es", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} s`;
}

export function reloj(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ---------- formato ligero de las respuestas ----------
// Las respuestas llegan como texto con viñetas («- ») y, a veces, **negritas**. Se convierten en bloques
// que la interfaz pinta como elementos, nunca como HTML: el texto es dato.

export interface Segmento {
  readonly texto: string;
  readonly negrita: boolean;
}

export type Bloque =
  | { readonly tipo: "parrafo"; readonly segmentos: readonly Segmento[] }
  | { readonly tipo: "lista"; readonly ordenada: boolean; readonly items: readonly (readonly Segmento[])[] };

export function segmentos(linea: string): Segmento[] {
  return linea
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((parte) => parte !== "")
    .map((parte) =>
      parte.length > 4 && parte.startsWith("**") && parte.endsWith("**")
        ? { texto: parte.slice(2, -2), negrita: true }
        : { texto: parte, negrita: false },
    );
}

export function bloquesDeTexto(texto: string): Bloque[] {
  const bloques: Bloque[] = [];
  let lista: { ordenada: boolean; items: Segmento[][] } | null = null;
  const cerrarLista = () => {
    if (lista) bloques.push({ tipo: "lista", ordenada: lista.ordenada, items: lista.items });
    lista = null;
  };
  for (const cruda of texto.split(/\r?\n/)) {
    const linea = cruda.trim();
    if (!linea) {
      cerrarLista();
      continue;
    }
    const vineta = /^[-•*]\s+(.+)$/.exec(linea);
    const numero = /^\d{1,2}[.)]\s+(.+)$/.exec(linea);
    const item = vineta ?? numero;
    if (item) {
      const ordenada = numero !== null;
      if (lista && lista.ordenada !== ordenada) cerrarLista();
      lista ??= { ordenada, items: [] };
      lista.items.push(segmentos(item[1] ?? ""));
      continue;
    }
    cerrarLista();
    const titulo = /^#{1,4}\s+(.+)$/.exec(linea);
    bloques.push({
      tipo: "parrafo",
      segmentos: titulo ? [{ texto: (titulo[1] ?? "").replaceAll("**", ""), negrita: true }] : segmentos(linea),
    });
  }
  cerrarLista();
  return bloques;
}
