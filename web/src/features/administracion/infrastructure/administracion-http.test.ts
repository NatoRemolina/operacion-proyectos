import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { resumenDePrueba } from "@/test/fabricas";
import { crearAdministracionHttp } from "./administracion-http";

function respuestaJson(cuerpo: unknown, estado = 200) {
  return new Response(JSON.stringify(cuerpo), {
    status: estado,
    headers: { "Content-Type": "application/json", "X-Peticion": "peticion-1" },
  });
}

function preparar(...respuestas: Response[]) {
  const fetchFalso = vi.fn<typeof fetch>();
  for (const r of respuestas) fetchFalso.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fetchFalso);
  return { fetchFalso, administracion: crearAdministracionHttp(crearClienteHttp("/api/v1")) };
}

async function errorDe(promesa: Promise<unknown>): Promise<ErrorDeAplicacion> {
  try {
    await promesa;
  } catch (error) {
    expect(error).toBeInstanceOf(ErrorDeAplicacion);
    return error as ErrorDeAplicacion;
  }
  throw new Error("Se esperaba un error");
}

afterEach(() => vi.unstubAllGlobals());

describe("adaptador HTTP de administración", () => {
  it("lee el resumen con la forma del contrato", async () => {
    const { fetchFalso, administracion } = preparar(respuestaJson(resumenDePrueba()));
    const resumen = await administracion.resumen();
    expect(resumen.presupuesto_aprobado_usd).toBe("15000.00");
    expect(resumen.actividad[0]?.persona?.nombre).toBe("Alex Rivera");
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/resumen");
  });

  it("403 es «sin permiso»", async () => {
    const { administracion } = preparar(
      respuestaJson({ error: { code: "FORBIDDEN", message: "x" }, request_id: "r1" }, 403),
    );
    expect((await errorDe(administracion.resumen())).tipo).toBe("prohibido");
  });

  it("una respuesta con otra forma es un error de contrato", async () => {
    const { administracion } = preparar(respuestaJson({ ...resumenDePrueba(), gastado_usd: 12.5 }));
    expect((await errorDe(administracion.resumen())).tipo).toBe("contrato");
  });
});
