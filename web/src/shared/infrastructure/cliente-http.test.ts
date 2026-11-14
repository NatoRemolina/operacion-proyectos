import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "./cliente-http";

function errorApi(estado: number, code: string, message = "Mensaje del servidor.", fields: Record<string, string> = {}) {
  return new Response(JSON.stringify({ error: { code, message, fields }, request_id: "r1" }), {
    status: estado,
    headers: { "Content-Type": "application/json" },
  });
}

async function errorDe(respuesta: Response): Promise<ErrorDeAplicacion> {
  vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValueOnce(respuesta));
  try {
    await crearClienteHttp("/api/v1").postJson("/x", {}, z.object({}));
  } catch (error) {
    return error as ErrorDeAplicacion;
  }
  throw new Error("Se esperaba un error");
}

afterEach(() => vi.unstubAllGlobals());

describe("cliente HTTP: códigos de administración", () => {
  it("aprobar lo propio se distingue de no tener permiso y conserva el mensaje", async () => {
    const error = await errorDe(errorApi(403, "SELF_APPROVAL", "Nadie aprueba ni rechaza su propio presupuesto."));
    expect(error.tipo).toBe("autoaprobacion");
    expect(error.message).toBe("Nadie aprueba ni rechaza su propio presupuesto.");
  });

  it("un precio por confirmar trae el cambio en el campo «precio»", async () => {
    const error = await errorDe(
      errorApi(409, "PRICE_CONFIRMATION_REQUIRED", "El precio cambió.", { precio: "antes 410.00 USD, ahora 451.00 USD" }),
    );
    expect(error.tipo).toBe("precio_por_confirmar");
    expect(error.campos.precio).toBe("antes 410.00 USD, ahora 451.00 USD");
  });

  it("un envío que todavía se procesa pide reintentar con la misma clave: no es un conflicto", async () => {
    const error = await errorDe(errorApi(409, "REQUEST_IN_PROGRESS"));
    expect(error.tipo).toBe("en_curso");
  });

  it("un estado que ya no admite la acción y un cambio ajeno tienen su propio tipo", async () => {
    expect((await errorDe(errorApi(409, "INVALID_STATE"))).tipo).toBe("estado_invalido");
    expect((await errorDe(errorApi(409, "EDIT_CONFLICT"))).tipo).toBe("cambio_ajeno");
  });
});

describe("cliente HTTP: cabeceras en escrituras JSON", () => {
  it("postJson manda las cabeceras pedidas (por ejemplo, Idempotency-Key) junto al token CSRF", async () => {
    const fetchFalso = vi.fn<typeof fetch>().mockResolvedValueOnce(
      new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchFalso);
    const cliente = crearClienteHttp("/api/v1");
    cliente.fijarCsrf("token-1");
    await cliente.postJson("/x", { a: 1 }, z.object({}), { cabeceras: { "Idempotency-Key": "clave-1" } });
    const cabeceras = new Headers(fetchFalso.mock.calls[0]![1]?.headers);
    expect(cabeceras.get("Idempotency-Key")).toBe("clave-1");
    expect(cabeceras.get("X-CSRF-Token")).toBe("token-1");
    expect(cabeceras.get("Content-Type")).toBe("application/json");
  });
});

describe("cliente HTTP: plazo y respuestas de quien está delante de la API (B8)", () => {
  it("el tope del día que explica la API se distingue del exceso de peticiones del borde", async () => {
    const tope = await errorDe(errorApi(429, "TOO_MANY_REQUESTS", "Llegaste al tope de 10 cotizaciones de hoy."));
    expect(tope.tipo).toBe("demasiados_intentos");
    // El WAF responde con su propio código cuando una dirección pasa la tasa permitida
    expect((await errorDe(errorApi(429, "RATE_LIMITED"))).tipo).toBe("ocupado");
    expect((await errorDe(new Response("Rate Exceeded.", { status: 429 }))).tipo).toBe("ocupado");
  });

  it("un servicio no disponible de la API trae su explicación", async () => {
    const error = await errorDe(errorApi(503, "SERVICE_UNAVAILABLE", "La transcripción no está configurada."));
    expect(error.tipo).toBe("no_disponible");
    expect(error.message).toBe("La transcripción no está configurada.");
  });

  it("un 409 sin código propio no habla de archivos: vale para cualquier pantalla", async () => {
    const error = await errorDe(new Response(null, { status: 409 }));
    expect(error.tipo).toBe("conflicto");
    expect(error.message).not.toMatch(/archivo/);
  });

  it("cancelar la petición (por ejemplo, al salir de la pantalla) no se confunde con un plazo agotado", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(
        (_url, init) =>
          new Promise<Response>((_r, rechazar) =>
            init?.signal?.addEventListener("abort", () => rechazar(new DOMException("Cancelada", "AbortError"))),
          ),
      ),
    );
    const control = new AbortController();
    const pedido = crearClienteHttp("/api/v1").get("/x", z.object({}), { signal: control.signal });
    control.abort();
    await expect(pedido).rejects.toMatchObject({ name: "AbortError" });
  });

  it("cada llamada puede pedir su propio plazo", async () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal(
        "fetch",
        vi.fn<typeof fetch>(
          (_url, init) =>
            new Promise<Response>((_r, rechazar) => init?.signal?.addEventListener("abort", () => rechazar(init.signal!.reason))),
        ),
      );
      const pedido = crearClienteHttp("/api/v1").postJson("/x", {}, z.object({}), { plazoMs: 5000 }).catch((e: unknown) => e);
      await vi.advanceTimersByTimeAsync(5000);
      expect(await pedido).toMatchObject({ tipo: "tiempo_agotado" });
    } finally {
      vi.useRealTimers();
    }
  });
});
