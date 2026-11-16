import { z } from "zod";
import { ErrorDeAplicacion, type TipoError } from "@/shared/domain/errores";

/**
 * Único punto que conoce `fetch`. Envía la cookie de sesión, nunca usa caché del navegador,
 * añade `X-CSRF-Token` en toda escritura, corta cada petición en su plazo y traduce los errores HTTP a errores de
 * aplicación.
 */

/** Plazo de una petición corriente: leer una lista, guardar un cambio. */
export const PLAZO_MS = 30_000;
/**
 * Plazo de lo que espera a un servicio externo (buscador, modelo, asesor): el mismo minuto que CloudFront le da a la
 * API. Pasado ese tiempo la respuesta ya no llegaría (CloudFront responde 504), pero lo pedido puede seguir en curso.
 */
export const PLAZO_LARGO_MS = 60_000;

const errorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string().optional(),
    fields: z.record(z.string(), z.string()).optional(),
  }),
  request_id: z.string().optional(),
});

const POR_CODIGO: Record<string, TipoError> = {
  UNAUTHENTICATED: "sesion_vencida",
  INVALID_CREDENTIALS: "credenciales",
  TOO_MANY_ATTEMPTS: "demasiados_intentos",
  CSRF_INVALID: "sesion_vencida",
  ORIGIN_NOT_ALLOWED: "prohibido",
  FORBIDDEN: "prohibido",
  NOT_FOUND: "no_encontrado",
  IDEMPOTENCY_CONFLICT: "conflicto",
  PAYLOAD_TOO_LARGE: "demasiado_grande",
  UNSUPPORTED_MEDIA_TYPE: "tipo_no_admitido",
  VALIDATION_ERROR: "validacion",
  SELF_APPROVAL: "autoaprobacion",
  INVALID_STATE: "estado_invalido",
  PRICE_CONFIRMATION_REQUIRED: "precio_por_confirmar",
  EDIT_CONFLICT: "cambio_ajeno",
  // El primer envío con esa clave aún no creó su gasto: se reintenta con la misma clave, no es un conflicto.
  REQUEST_IN_PROGRESS: "en_curso",
  CONFLICT: "conflicto",
  // El tope del día que explica la API (cotizaciones, lecturas): no es el exceso de peticiones del borde.
  TOO_MANY_REQUESTS: "demasiados_intentos",
  // El WAF de CloudFront, cuando una dirección pasa la tasa permitida (infra/lib/web-stack.ts).
  RATE_LIMITED: "ocupado",
  SERVICE_UNAVAILABLE: "no_disponible",
  INTERNAL_ERROR: "servidor",
};

const CON_MENSAJE_DEL_SERVIDOR: readonly TipoError[] = [
  "validacion",
  "autoaprobacion",
  "estado_invalido",
  "precio_por_confirmar",
  "no_disponible",
];

function tipoPorEstado(estado: number): TipoError {
  if (estado === 401) return "sesion_vencida";
  if (estado === 403) return "prohibido";
  if (estado === 404) return "no_encontrado";
  if (estado === 409) return "conflicto";
  if (estado === 413) return "demasiado_grande";
  if (estado === 415) return "tipo_no_admitido";
  if (estado === 422) return "validacion";
  // Sin el JSON de la API, un 429 viene de delante de ella: la función en pausa o sin turno, o el WAF
  if (estado === 429) return "ocupado";
  if (estado === 502 || estado === 503) return "no_disponible";
  // CloudFront corta a los 60 s: lo pedido puede seguir en curso en la API
  if (estado === 504) return "tiempo_agotado";
  return "servidor";
}

async function errorDesdeRespuesta(respuesta: Response): Promise<ErrorDeAplicacion> {
  const idCabecera = respuesta.headers.get("X-Peticion");
  let cuerpo: unknown = null;
  try {
    cuerpo = await respuesta.json();
  } catch {
    // Un error sin JSON (por ejemplo, del gateway) se clasifica solo por su estado.
  }
  const leido = errorSchema.safeParse(cuerpo);
  if (!leido.success) {
    return new ErrorDeAplicacion(tipoPorEstado(respuesta.status), { idPeticion: idCabecera });
  }
  const { error, request_id } = leido.data;
  const tipo = POR_CODIGO[error.code] ?? tipoPorEstado(respuesta.status);
  return new ErrorDeAplicacion(tipo, {
    // El texto del servidor solo se usa donde explica qué corregir o qué cambió (viene en lenguaje claro).
    mensaje: CON_MENSAJE_DEL_SERVIDOR.includes(tipo) ? error.message : undefined,
    campos: error.fields,
    idPeticion: request_id ?? idCabecera,
  });
}

/** `plazoMs`: cuánto se espera antes de cortar la petición con «tiempo_agotado» (por omisión, `PLAZO_MS`). */
interface OpcionesPeticion {
  signal?: AbortSignal;
  plazoMs?: number;
}

export interface ClienteHttp {
  get<T>(ruta: string, esquema: z.ZodType<T>, opciones?: OpcionesPeticion): Promise<T>;
  postJson<T>(
    ruta: string,
    cuerpo: unknown,
    esquema: z.ZodType<T>,
    /** `cabeceras`: por ejemplo `Idempotency-Key` en una escritura que puede reintentarse. */
    opciones?: OpcionesPeticion & { csrf?: boolean; cabeceras?: Record<string, string> },
  ): Promise<T>;
  postFormulario<T>(
    ruta: string,
    formulario: FormData,
    esquema: z.ZodType<T>,
    opciones?: OpcionesPeticion & { cabeceras?: Record<string, string> },
  ): Promise<T>;
  postSinRespuesta(ruta: string, opciones?: OpcionesPeticion): Promise<void>;
  url(ruta: string): string;
  fijarCsrf(token: string | null): void;
}

/**
 * Corre `trabajo` con una señal que se cancela al cumplirse el plazo o si quien llama cancela (React Query al salir
 * de la pantalla). El plazo cubre también la lectura del cuerpo. Solo el plazo se traduce a «tiempo_agotado»: una
 * cancelación de quien llama sigue siendo una cancelación.
 */
async function conPlazo<T>(
  plazoMs: number,
  externa: AbortSignal | undefined,
  trabajo: (senal: AbortSignal) => Promise<T>,
): Promise<T> {
  const control = new AbortController();
  let agotado = false;
  const reloj = setTimeout(() => {
    agotado = true;
    control.abort(new DOMException("Plazo agotado", "TimeoutError"));
  }, plazoMs);
  const alCancelar = () => control.abort(externa?.reason);
  if (externa?.aborted) alCancelar();
  else externa?.addEventListener("abort", alCancelar, { once: true });
  try {
    return await trabajo(control.signal);
  } catch (causa) {
    if (agotado) throw new ErrorDeAplicacion("tiempo_agotado");
    throw causa;
  } finally {
    clearTimeout(reloj);
    externa?.removeEventListener("abort", alCancelar);
  }
}

export function crearClienteHttp(base: string): ClienteHttp {
  const raiz = base.replace(/\/+$/, "");
  let csrf: string | null = null;

  async function pedir(ruta: string, init: RequestInit & { signal: AbortSignal }, escritura: boolean): Promise<Response> {
    const cabeceras = new Headers(init.headers);
    cabeceras.set("Accept", "application/json");
    if (escritura && csrf) cabeceras.set("X-CSRF-Token", csrf);
    let respuesta: Response;
    try {
      respuesta = await fetch(`${raiz}${ruta}`, {
        ...init,
        headers: cabeceras,
        credentials: "include",
        cache: "no-store",
      });
    } catch (causa) {
      if (init.signal.aborted) throw causa;
      throw new ErrorDeAplicacion("red");
    }
    if (!respuesta.ok) throw await errorDesdeRespuesta(respuesta);
    return respuesta;
  }

  async function leer<T>(respuesta: Response, esquema: z.ZodType<T>, senal: AbortSignal): Promise<T> {
    let cuerpo: unknown;
    try {
      cuerpo = await respuesta.json();
    } catch (causa) {
      if (senal.aborted) throw causa;
      throw new ErrorDeAplicacion("contrato", {
        idPeticion: respuesta.headers.get("X-Peticion"),
      });
    }
    const leido = esquema.safeParse(cuerpo);
    if (!leido.success) {
      throw new ErrorDeAplicacion("contrato", {
        idPeticion: respuesta.headers.get("X-Peticion"),
      });
    }
    return leido.data;
  }

  return {
    get(ruta, esquema, opciones = {}) {
      return conPlazo(opciones.plazoMs ?? PLAZO_MS, opciones.signal, async (signal) =>
        leer(await pedir(ruta, { method: "GET", signal }, false), esquema, signal),
      );
    },
    postJson(ruta, cuerpo, esquema, opciones = {}) {
      return conPlazo(opciones.plazoMs ?? PLAZO_MS, opciones.signal, async (signal) => {
        const respuesta = await pedir(
          ruta,
          {
            method: "POST",
            body: JSON.stringify(cuerpo),
            headers: { ...opciones.cabeceras, "Content-Type": "application/json" },
            signal,
          },
          opciones.csrf ?? true,
        );
        return leer(respuesta, esquema, signal);
      });
    },
    postFormulario(ruta, formulario, esquema, opciones = {}) {
      return conPlazo(opciones.plazoMs ?? PLAZO_MS, opciones.signal, async (signal) => {
        // Sin Content-Type: el navegador pone el límite (boundary) del multipart.
        const respuesta = await pedir(ruta, { method: "POST", body: formulario, headers: opciones.cabeceras, signal }, true);
        return leer(respuesta, esquema, signal);
      });
    },
    postSinRespuesta(ruta, opciones = {}) {
      return conPlazo(opciones.plazoMs ?? PLAZO_MS, opciones.signal, async (signal) => {
        await pedir(ruta, { method: "POST", signal }, true);
      });
    },
    url(ruta) {
      return `${raiz}${ruta}`;
    },
    fijarCsrf(token) {
      csrf = token;
    },
  };
}

export const dineroSchema = z
  .string()
  .regex(/^-?\d+\.\d{2}$/)
  .nullable();

export function paginaSchema<T>(item: z.ZodType<T>) {
  return z.object({ items: z.array(item), siguiente: z.string().nullable() });
}

export function consulta(parametros: Record<string, string | number | null | undefined>): string {
  const busqueda = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor !== null && valor !== undefined && valor !== "") busqueda.set(clave, String(valor));
  }
  const texto = busqueda.toString();
  return texto ? `?${texto}` : "";
}
