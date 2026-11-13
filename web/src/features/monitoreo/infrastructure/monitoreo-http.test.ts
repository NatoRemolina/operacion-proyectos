import { afterEach, describe, expect, it, vi } from "vitest";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { GASTOS_EJEMPLO } from "./ejemplo-monitoreo";
import { crearMonitoreoHttp } from "./monitoreo-http";

afterEach(() => vi.restoreAllMocks());

describe("Monitoreo por HTTP", () => {
  it("pide la pestaña con los filtros y valida la respuesta", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(GASTOS_EJEMPLO), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const p = await crearMonitoreoHttp(crearClienteHttp("/api/v1")).pestana("gastos", { proyecto_id: 1, desde: null, hasta: "2026-11-30" });
    expect(fetch.mock.calls[0]![0]).toBe("/api/v1/monitoreo?pestana=gastos&proyecto_id=1&hasta=2026-11-30");
    expect(p.tablas).toHaveLength(3);
  });

  it("rechaza un enlace que no es de la web", async () => {
    const malo = { ...GASTOS_EJEMPLO, tablas: [{ ...GASTOS_EJEMPLO.tablas[1]!, filas: [[{ texto: "x", href: "https://otro.test" }, 1]] }] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(malo), { status: 200 }));
    await expect(crearMonitoreoHttp(crearClienteHttp("/api/v1")).pestana("gastos", { proyecto_id: null, desde: null, hasta: null })).rejects.toMatchObject({ tipo: "contrato" });
  });

  it("la descarga es un enlace con la vista y los filtros", () => {
    expect(crearMonitoreoHttp(crearClienteHttp("/api/v1")).urlExportar("v_h_evento", { proyecto_id: null, desde: "2026-11-01", hasta: null })).toBe(
      "/api/v1/monitoreo/exportar.csv?vista=v_h_evento&desde=2026-11-01",
    );
  });
});
