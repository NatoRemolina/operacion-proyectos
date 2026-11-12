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
