import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion, mensajeDeError, type TipoError } from "@/shared/domain/errores";
import { crearClienteHttp, type ClienteHttp } from "@/shared/infrastructure/cliente-http";

/**
 * Lo que llega cuando responde quien está delante de la API y no la API misma (CloudFront, el WAF, Lambda o el
 * gateway local): solo el estado, sin el JSON de error del contrato. Cada caso tiene su tipo y su mensaje propio.
 */
export const SIN_CUERPO_DE_LA_API: ReadonlyArray<readonly [number, TipoError]> = [
  [401, "sesion_vencida"],
  [403, "prohibido"],
  [409, "conflicto"],
  [429, "ocupado"],
  [500, "servidor"],
  [502, "no_disponible"],
  [503, "no_disponible"],
  [504, "tiempo_agotado"],
];

/** Un servidor que nunca contesta: la petición solo termina si alguien la cancela. */
function fetchColgado() {
  return vi.fn<typeof fetch>(
    (_url, init) =>
      new Promise<Response>((_resolver, rechazar) => {
        const senal = init?.signal;
        senal?.addEventListener("abort", () => rechazar(senal.reason ?? new DOMException("Cancelada", "AbortError")));
      }),
  );
}

export interface LlamadaHttp<R> {
  llamar: (repositorio: R) => Promise<unknown>;
  /** El plazo que se le da a esta llamada antes de cortarla. */
  plazoMs: number;
}

/**
 * Prueba común de un repositorio HTTP (B8):
 * - cada llamada tiene su plazo: un servidor que no contesta se corta justo ahí, con un mensaje claro;
 * - ante 401, 403, 409, 429 y 5xx sin el cuerpo de la API, el error trae su tipo y su mensaje, sin tragárselo.
 *
 * `representativa` es una llamada que no convierte ningún error en un resultado (la de 401 de «quién soy» sí lo hace).
 */
export function probarRepositorioHttp<R>(
  nombre: string,
  crear: (cliente: ClienteHttp) => R,
  llamadas: Record<string, LlamadaHttp<R>>,
  representativa: string,
) {
  describe(`repositorio HTTP de ${nombre}: plazos y errores (B8)`, () => {
    afterEach(() => {
      vi.useRealTimers();
      vi.unstubAllGlobals();
    });

    for (const [llamada, { llamar, plazoMs }] of Object.entries(llamadas)) {
      it(`${llamada} se corta a los ${plazoMs / 1000} s si el servidor no contesta`, async () => {
        vi.useFakeTimers();
        vi.stubGlobal("fetch", fetchColgado());
        let resultado: unknown = "pendiente";
        void llamar(crear(crearClienteHttp("/api/v1"))).then(
          () => (resultado = "respondió"),
          (error: unknown) => (resultado = error),
        );
        await vi.advanceTimersByTimeAsync(plazoMs - 1);
        expect(resultado).toBe("pendiente");
        await vi.advanceTimersByTimeAsync(1);
        expect(resultado).toBeInstanceOf(ErrorDeAplicacion);
        expect((resultado as ErrorDeAplicacion).tipo).toBe("tiempo_agotado");
        expect((resultado as ErrorDeAplicacion).message).toBe(mensajeDeError("tiempo_agotado"));
      });
    }

    const { llamar } = llamadas[representativa]!;
    for (const [estado, tipo] of SIN_CUERPO_DE_LA_API) {
      it(`${representativa}: un ${estado} sin cuerpo de la API se muestra como «${tipo}» con su mensaje`, async () => {
        vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(new Response("<html>Error</html>", { status: estado })));
        const error = await llamar(crear(crearClienteHttp("/api/v1"))).then(
          () => null,
          (e: unknown) => e,
        );
        expect(error).toBeInstanceOf(ErrorDeAplicacion);
        expect((error as ErrorDeAplicacion).tipo).toBe(tipo);
        expect((error as ErrorDeAplicacion).message).toBe(mensajeDeError(tipo));
      });
    }
  });
}
