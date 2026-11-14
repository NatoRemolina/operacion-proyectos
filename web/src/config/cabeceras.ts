/**
 * Política de contenido (CSP) de la web (B1). La pone Next en todas las rutas (next.config.ts); CloudFront añade HSTS,
 * nosniff, marco propio y Referrer-Policy (infra/lib/web-stack.ts).
 *
 * Solo recursos propios. Dos concesiones, explicadas:
 * - `script-src 'unsafe-inline'`: Next arranca la página con scripts en línea, y un nonce exigiría generar cada página
 *   por petición. Los demás orígenes de script siguen prohibidos, y los enlaces que se pintan pasan por el esquema
 *   común (shared/domain/enlaces.ts), que no deja `javascript:`.
 * - `style-src 'unsafe-inline'`: los estilos en línea de React (`style={…}`).
 */
function origenDe(baseApi: string): string | null {
  try {
    return new URL(baseApi).origin;
  } catch {
    return null;   // relativa (/api/v1): el mismo origen de la web
  }
}

export function politicaDeContenido({ desarrollo, baseApi }: { desarrollo: boolean; baseApi: string }): string {
  const api = origenDe(baseApi);
  const propio = (...extra: Array<string | null>) => ["'self'", ...extra.filter((x): x is string => Boolean(x))];
  const directivas: Record<string, string[]> = {
    "default-src": propio(),
    // En desarrollo, la recarga en caliente de Next evalúa código
    "script-src": propio("'unsafe-inline'", desarrollo ? "'unsafe-eval'" : null),
    "style-src": propio("'unsafe-inline'"),
    // data: y blob: para la vista previa del recibo; la API sirve capturas y soportes
    "img-src": propio("data:", "blob:", api),
    "media-src": propio("blob:", api),
    "font-src": propio(),
    "connect-src": propio(api),
    "object-src": ["'none'"],
    "base-uri": propio(),
    "form-action": propio(),
    "frame-ancestors": propio(),
  };
  return Object.entries(directivas)
    .map(([nombre, valores]) => `${nombre} ${valores.join(" ")}`)
    .join("; ");
}
