import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { crearReglasHttp } from "./reglas-http";

const REGLA = {
  id: 26, ambito: "supuesto", entidad: "", tarifa: "", clave: "tolerancia_presupuesto", valor: "0.1", numerica: true,
  nota: "Holgura", fuente: "Supuesto", confianza: "supuesto", verificado: "2026-11-11",
};

function respuestaJson(cuerpo: unknown, estado = 200) {
  return new Response(JSON.stringify(cuerpo), { status: estado, headers: { "Content-Type": "application/json" } });
}

function preparar(...respuestas: Response[]) {
  const fetchFalso = vi.fn<typeof fetch>();
  for (const r of respuestas) fetchFalso.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fetchFalso);
  return { fetchFalso, reglas: crearReglasHttp(crearClienteHttp("/api/v1")) };
}

afterEach(() => vi.unstubAllGlobals());

describe("adaptador HTTP de reglas", () => {
  it("lee el catálogo agrupado con las membresías", async () => {
    const { fetchFalso, reglas } = preparar(
      respuestaJson({
        grupos: [{ clave: "supuesto", titulo: "Supuestos", reglas: [REGLA] }],
        membresias: [{ id: 1, titular: "Empresa", de_empresa: true, programa: "AAdvantage", entidad: "American", estatus: "", ejemplo: true }],
      }),
    );
    const catalogo = await reglas.catalogoReglas();
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/reglas");
    expect(catalogo.grupos[0]?.reglas[0]?.numerica).toBe(true);
    expect(catalogo.membresias[0]?.ejemplo).toBe(true);
  });

  it("edita con POST y el valor en el cuerpo", async () => {
    const { fetchFalso, reglas } = preparar(respuestaJson({ ...REGLA, valor: "0.25" }));
    const regla = await reglas.editarRegla(26, "0.25");
    const [ruta, init] = fetchFalso.mock.calls[0]!;
    expect(ruta).toBe("/api/v1/reglas/26");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ valor: "0.25" });
    expect(regla.valor).toBe("0.25");
  });

  it("un valor que no sirve llega como «validacion» con el porqué del servidor", async () => {
    const { reglas } = preparar(
      respuestaJson({ error: { code: "VALIDATION_ERROR", message: "Hay datos que no son válidos.", fields: { valor: "«x» no es un número válido para t." } }, request_id: "r" }, 422),
    );
    const error = await reglas.editarRegla(26, "x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ErrorDeAplicacion);
    expect((error as ErrorDeAplicacion).campos.valor).toBe("«x» no es un número válido para t.");
  });
});
