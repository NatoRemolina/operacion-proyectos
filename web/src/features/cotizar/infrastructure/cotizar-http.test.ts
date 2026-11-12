import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { BORRADOR_VACIO, borradorDeEjemplo, pedidoDesdeBorrador } from "../domain/cotizar";
import { crearCotizarHttp } from "./cotizar-http";
import { COTIZACION_MOAB, FORMULARIO_EJEMPLO, LUGARES_EJEMPLO } from "./ejemplo-moab";

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
  const cliente = crearClienteHttp("/api/v1");
  cliente.fijarCsrf("token-csrf");
  return { fetchFalso, cotizar: crearCotizarHttp(cliente) };
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

describe("adaptador HTTP de cotizar", () => {
  it("lugares: pide con sesión y sin caché, con o sin Google", async () => {
    const { fetchFalso, cotizar } = preparar(respuestaJson(LUGARES_EJEMPLO.moab), respuestaJson(LUGARES_EJEMPLO.moab));
    const lista = await cotizar.buscarLugares("moab ", false);
    expect(lista.resultados[0]?.aeropuertos.map((a) => a.iata)).toEqual(["CNY", "GJT", "SLC"]);
    await cotizar.buscarLugares("moab", true);
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/lugares?q=moab&limite=8");
    expect(fetchFalso.mock.calls[1]![0]).toBe("/api/v1/lugares?q=moab&google=1&limite=8");
    expect(fetchFalso.mock.calls[0]![1]?.credentials).toBe("include");
  });

  it("cotizar: envía el pedido en JSON con el token CSRF y valida la comparación", async () => {
    const { fetchFalso, cotizar } = preparar(respuestaJson(COTIZACION_MOAB, 201));
    const pedido = pedidoDesdeBorrador({ ...borradorDeEjemplo(BORRADOR_VACIO), proyectoId: "1", viajeroId: "1" }, 1);
    const c = await cotizar.cotizar(pedido);
    expect(c.recomendada_id).toBe(COTIZACION_MOAB.recomendada_id);
    const [url, init] = fetchFalso.mock.calls[0]!;
    expect(url).toBe("/api/v1/cotizaciones");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("token-csrf");
    expect(JSON.parse(String(init?.body))).toMatchObject({ viajero_id: null, destino: { aeropuertos: ["CNY", "GJT", "SLC"] } });
  });

  it("formulario y detalle se validan contra el contrato", async () => {
    const { cotizar } = preparar(respuestaJson(FORMULARIO_EJEMPLO), respuestaJson({ ...COTIZACION_MOAB, vuelos: [{ id: 1 }] }));
    expect((await cotizar.formulario()).razones.length).toBeGreaterThan(0);
    expect((await errorDe(cotizar.obtener(7))).tipo).toBe("contrato");
  });

  it("422: los campos del servidor llegan a la interfaz", async () => {
    const { cotizar } = preparar(
      respuestaJson({ error: { code: "VALIDATION_ERROR", message: "Hay datos que no son válidos.", fields: { destino: "No reconozco \"ZZZ\"." } }, request_id: "r1" }, 422),
    );
    const error = await errorDe(cotizar.decidir(7, { vuelo_id: 1, hotel_id: null, motivo: "", razones: [] }));
    expect(error.tipo).toBe("validacion");
    expect(error.campos).toEqual({ destino: "No reconozco \"ZZZ\"." });
  });

  it("decidir: la decisión bloqueada llega como conflicto", async () => {
    const { fetchFalso, cotizar } = preparar(
      respuestaJson({ error: { code: "DECISION_LOCKED", message: "El viaje ya está aprobado." }, request_id: "r2" }, 409),
    );
    const error = await errorDe(cotizar.decidir(7, { vuelo_id: 1, hotel_id: null, motivo: "", razones: ["horario"] }));
    expect(error.tipo).toBe("conflicto");
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/cotizaciones/7/decision");
  });
});
