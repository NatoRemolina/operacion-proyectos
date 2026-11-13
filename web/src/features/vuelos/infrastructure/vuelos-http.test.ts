import { afterEach, describe, expect, it, vi } from "vitest";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { TRAMO_EJEMPLO } from "./ejemplo-vuelos";
import { crearVuelosHttp } from "./vuelos-http";

afterEach(() => vi.restoreAllMocks());

function responder(cuerpo: unknown) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify(cuerpo), { status: 200 }));
}

describe("Vuelos por HTTP", () => {
  it("pide los vuelos del día y, sin fecha, los de hoy", async () => {
    const fetch = responder({ fecha: null, hoy: "2026-12-13", tramos: [TRAMO_EJEMPLO] });
    const repo = crearVuelosHttp(crearClienteHttp("/api/v1"));
    expect((await repo.delDia(null)).tramos[0]!.origen_texto).toBe("Estado de ejemplo");
    expect(fetch.mock.calls[0]![0]).toBe("/api/v1/vuelos");
    await repo.delDia("2026-12-13");
    expect(fetch.mock.calls[1]![0]).toBe("/api/v1/vuelos?fecha=2026-12-13");
  });

  it("«Actualizar» es una escritura con el token de la sesión", async () => {
    const fetch = responder({ consultado: true, motivo: null, mensaje: "IB 5634: estado actualizado.", tramo: TRAMO_EJEMPLO });
    const cliente = crearClienteHttp("/api/v1");
    cliente.fijarCsrf("token-de-prueba");
    const r = await crearVuelosHttp(cliente).actualizar(41);
    expect(r.consultado).toBe(true);
    const [url, init] = fetch.mock.calls[0]!;
    expect(url).toBe("/api/v1/vuelos/41/actualizar");
    expect(init!.method).toBe("POST");
    expect(new Headers(init!.headers).get("X-CSRF-Token")).toBe("token-de-prueba");
  });
});
