/** Importe en decimal canónico con dos cifras ("54.00"); `null` si no se pudo leer. Nunca float. */
export type Dinero = string | null;

/** Fecha sin hora, "2026-12-09". */
export type FechaISO = string;

export interface Pagina<T> {
  readonly items: readonly T[];
  readonly siguiente: string | null;
}

export interface OpcionesListado {
  readonly limite?: number;
  readonly cursor?: string | null;
}
