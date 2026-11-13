import { afterEach, describe, expect, it, vi } from "vitest";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { crearComprasHttp } from "./compras-http";
import { COMPRA_EJEMPLO } from "./ejemplo-compras";

function preparar(cuerpo: unknown) {
  const fetchFalso = vi.fn<typeof fetch>();
  fetchFalso.mockResolvedValueOnce(
    new Response(JSON.stringify(cuerpo), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchFalso);
  return crearComprasHttp(crearClienteHttp("/api/v1"));
}

afterEach(() => vi.unstubAllGlobals());

describe("adaptador HTTP de compras", () => {
  it("el enlace a Google Flights del vuelo solo pasa si es de Google (como en cotizar)", async () => {
    const bueno = await preparar(COMPRA_EJEMPLO).detalle(7);
    expect(bueno.vuelo!.fuente_url).toBe(COMPRA_EJEMPLO.vuelo!.fuente_url);
    for (const malo of ["javascript:alert(1)", "https://google.com.evil.example/travel/flights", "http://www.google.com/travel/flights"]) {
      const d = await preparar({ ...COMPRA_EJEMPLO, vuelo: { ...COMPRA_EJEMPLO.vuelo!, fuente_url: malo } }).detalle(7);
      expect(d.vuelo!.fuente_url, malo).toBeNull();
    }
  });
});
