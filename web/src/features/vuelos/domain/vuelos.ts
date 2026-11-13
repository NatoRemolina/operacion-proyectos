/** Estado de los vuelos del día (solo administración). Mismo contrato que `GET /api/v1/vuelos`. */

export interface AvisoVuelo {
  readonly momento?: string | null;
  readonly texto?: string | null;
  readonly enviado?: boolean | null;
  readonly error?: string | null;
}

export interface TramoVuelo {
  readonly id: number;
  readonly viaje_id: number;
  readonly codigo: string;
  readonly titular: string | null;
  readonly sentido: string;
  readonly aerolinea: string | null;
  readonly numero: string;
  readonly fecha: string;
  readonly desde: string | null;
  readonly hasta: string | null;
  readonly sale_programada: string | null;
  readonly llega_programada: string | null;
  readonly llega_estimada: string | null;
  readonly estado: string | null;
  readonly estado_texto: string;
  readonly retraso: number;
  readonly terminal: string | null;
  readonly puerta: string | null;
  readonly consultas: number | null;
  readonly hace_min: number | null;
  readonly llegar_antes: string | null;
  readonly en_destino: string | null;
  readonly no_llega: boolean;
  readonly omitida: string | null;
  readonly ultima_consulta: string | null;
  readonly aviso: AvisoVuelo | null;
  readonly origen: string | null;
  readonly origen_texto: string | null;
}

export interface VuelosDelDia {
  readonly fecha: string | null;
  readonly hoy: string;
  readonly tramos: readonly TramoVuelo[];
}

export interface ResultadoActualizacion {
  readonly consultado: boolean;
  readonly motivo: string | null;
  readonly mensaje: string;
  readonly tramo: TramoVuelo | null;
}

export interface VuelosRepository {
  /** Solo administración; para otro permiso falla con «prohibido». Sin fecha: hoy y los vuelos en curso. */
  delDia(fecha: string | null, signal?: AbortSignal): Promise<VuelosDelDia>;
  /** «Actualizar ahora»: salta la caché, nunca la ventana ni los topes. */
  actualizar(tramoId: number): Promise<ResultadoActualizacion>;
}

/** Cada 15 s, como el tablero de hoy; solo con la pestaña visible. */
export const REFRESCO_MS = 15_000;

export function leerFecha(valor: unknown): string | null {
  return typeof valor === "string" && /^\d{4}-\d{2}-\d{2}$/.test(valor) ? valor : null;
}

/** «09:05» de «2026-12-13 09:05»: las horas son locales de cada aeropuerto. */
export function hora(local: string | null): string {
  return local && local.length >= 16 ? local.slice(11, 16) : "—";
}

export function tonoDeVuelo(estado: string | null): "exito" | "aviso" | "error" | "neutro" {
  if (estado === "cancelado") return "error";
  if (estado === "retrasado" || estado === "desviado" || estado === "sin datos") return "aviso";
  if (estado === "a tiempo" || estado === "aterrizado") return "exito";
  return "neutro";
}

/** Hace cuánto se consultó y cuántas veces, en palabras. */
export function textoActualizado(t: Pick<TramoVuelo, "hace_min" | "consultas">): string {
  const cuando = t.hace_min === null ? "Sin consultar" : t.hace_min === 0 ? "Hace menos de 1 min" : `Hace ${t.hace_min} min`;
  const n = t.consultas ?? 0;
  return `${cuando} · ${n} ${n === 1 ? "consulta" : "consultas"}`;
}

/** El último aviso al viajero y por dónde salió. */
export function textoAviso(aviso: AvisoVuelo | null): string | null {
  if (!aviso?.texto) return null;
  const canal = aviso.enviado
    ? "enviado por Telegram"
    : aviso.error
      ? `no se pudo enviar por Telegram: ${aviso.error}`
      : "solo en este tablero: no tiene Telegram vinculado";
  return `Último aviso al viajero (${aviso.momento ?? "—"} UTC, ${canal}): ${aviso.texto}`;
}
