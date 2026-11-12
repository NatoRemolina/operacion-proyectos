import type { Dinero } from "@/shared/domain/tipos";

const LOCALE = "es-CO";

/**
 * Intl.NumberFormat acepta la cadena decimal tal cual, sin pasar por float,
 * así "0.10" + redondeos nunca alteran lo que dice el servidor.
 */
export function formatearDinero(valor: Dinero, moneda: string | null = "USD"): string {
  if (valor === null) return "Importe por confirmar";
  if (!moneda) return `${valor} (moneda por confirmar)`;
  try {
    return new Intl.NumberFormat(LOCALE, { style: "currency", currency: moneda }).format(
      valor as unknown as number,
    );
  } catch {
    return `${moneda} ${valor}`;
  }
}

function aFecha(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

export function formatearFecha(iso: string | null): string {
  if (!iso) return "Fecha por confirmar";
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(aFecha(iso));
}

export function formatearRango(ida: string, regreso: string): string {
  return `${formatearFecha(ida)} – ${formatearFecha(regreso)}`;
}

export function formatearInstante(iso: string): string {
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" }).format(fecha);
}

export function formatearTamano(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString(LOCALE, { maximumFractionDigits: 1 })} MB`;
}
