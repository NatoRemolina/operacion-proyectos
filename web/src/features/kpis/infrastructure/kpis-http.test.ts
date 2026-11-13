import { afterEach, describe, expect, it, vi } from "vitest";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { FICHA_EJEMPLO, TABLERO_EJEMPLO } from "./ejemplo-kpis";
import { crearKpisHttp } from "./kpis-http";

function responder(cuerpo: unknown, estado = 200) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(cuerpo), { status: estado, headers: { "Content-Type": "application/json" } }),
  );
}

afterEach(() => vi.restoreAllMocks());

describe("KPIs por HTTP", () => {
  it("pide el tablero con los filtros que tienen valor y valida la respuesta", async () => {
    const fetch = responder(TABLERO_EJEMPLO);
    const repo = crearKpisHttp(crearClienteHttp("/api/v1"));
    const t = await repo.tablero({ proyecto_id: 1, desde: "2026-11-01", hasta: null });
    expect(fetch.mock.calls[0]![0]).toBe("/api/v1/kpis?proyecto_id=1&desde=2026-11-01");
    expect(t.kpis).toHaveLength(3);
  });

  it("pide la ficha de una persona", async () => {
    const fetch = responder(FICHA_EJEMPLO);
    const p = await crearKpisHttp(crearClienteHttp("/api/v1")).ficha(2);
    expect(fetch.mock.calls[0]![0]).toBe("/api/v1/kpis/personas/2");
    expect(p.usuario.codigo).toBe("P-0002");
  });

  it("una respuesta con otra forma es un error de contrato", async () => {
    responder({ kpis: "no" });
    await expect(crearKpisHttp(crearClienteHttp("/api/v1")).tablero({ proyecto_id: null, desde: null, hasta: null })).rejects.toMatchObject({ tipo: "contrato" });
  });

  it("sin permiso es «prohibido»", async () => {
    responder({ error: { code: "FORBIDDEN", message: "Solo administración" }, request_id: "x" }, 403);
    await expect(crearKpisHttp(crearClienteHttp("/api/v1")).ficha(2)).rejects.toMatchObject({ tipo: "prohibido" });
  });

  it("la descarga es un enlace con los mismos filtros", () => {
    const url = crearKpisHttp(crearClienteHttp("https://api.ejemplo.test/api/v1")).urlExportar("personas", { proyecto_id: 2, desde: null, hasta: "2026-11-30" });
    expect(url).toBe("https://api.ejemplo.test/api/v1/kpis/exportar.csv?que=personas&proyecto_id=2&hasta=2026-11-30");
  });
});
