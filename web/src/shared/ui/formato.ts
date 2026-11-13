import type { Dinero } from "@/shared/domain/tipos";

const LOCALE = "es-CO";

/**
 * Intl.NumberFormat acepta la cadena decimal tal cual, sin pasar por float,
 * así "0.10" + redondeos nunca alteran lo que dice el servidor. La moneda va por su código
 * («USD 1.672,00»): «US$» y «$» se confunden con el peso.
 */
export function formatearDinero(valor: Dinero, moneda: string | null = "USD"): string {
  if (valor === null) return "Importe por confirmar";
  if (!moneda) return `${valor} (moneda por confirmar)`;
  try {
    return new Intl.NumberFormat(LOCALE, {
      style: "currency",
      currency: moneda,
      currencyDisplay: "code",
    })
      .format(valor as unknown as number)
      .replace(/\u00a0/g, " ");
  } catch {
    return `${moneda} ${valor}`;
  }
}

function aFecha(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

const FECHA = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

/** «9 dic 2026»: sin los «de» ni el punto de la abreviatura que pone es-CO. */
export function formatearFecha(iso: string | null): string {
  if (!iso) return "Fecha por confirmar";
  const fecha = aFecha(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  const partes = Object.fromEntries(FECHA.formatToParts(fecha).map((p) => [p.type, p.value]));
  return `${partes.day} ${(partes.month ?? "").replace(".", "")} ${partes.year}`;
}

export function formatearRango(ida: string, regreso: string): string {
  return `${formatearFecha(ida)} – ${formatearFecha(regreso)}`;
}

/** La base guarda los instantes en UTC sin zona («AAAA-MM-DD HH:MM:SS»): sin zona se leen como UTC, no como hora local. */
function instanteUtc(iso: string): Date {
  const texto = iso.trim().replace(" ", "T");
  const conZona = /([zZ]|[+-]\d{2}:?\d{2})$/.test(texto) || !texto.includes("T");
  return new Date(conZona ? texto : `${texto}Z`);
}

export function formatearInstante(iso: string): string {
  const fecha = instanteUtc(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat(LOCALE, { dateStyle: "medium", timeStyle: "short" }).format(fecha);
}

export function formatearTamano(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString(LOCALE, { maximumFractionDigits: 1 })} MB`;
}
