import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { proyectoDePrueba, tableroDePrueba } from "../test/fabricas";
import { crearProyectosHttp } from "./proyectos-http";

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
  return { fetchFalso, proyectos: crearProyectosHttp(cliente) };
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

describe("adaptador HTTP de proyectos", () => {
  it("lista con límite y cursor", async () => {
    const { fetchFalso, proyectos } = preparar(respuestaJson({ items: [proyectoDePrueba()], siguiente: "4" }));
    const pagina = await proyectos.listar({ limite: 20, cursor: "9" });
    expect(pagina.items[0]?.previsto_usd).toBe("1500.00");
    expect(pagina.siguiente).toBe("4");
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/proyectos?limite=20&cursor=9");
  });

  it("lee el tablero con la forma del contrato", async () => {
    const { fetchFalso, proyectos } = preparar(respuestaJson(tableroDePrueba()));
    const tablero = await proyectos.obtener(1);
    expect(tablero.categorias[0]?.clave).toBe("vuelo");
    expect(tablero.gastos[0]?.viajero).toBe("Alex Rivera");
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/proyectos/1");
  });

  it("crear envía el JSON con el token CSRF", async () => {
    const { fetchFalso, proyectos } = preparar(respuestaJson(proyectoDePrueba({ id: 9 }), 201));
    const datos = { nombre: "Torre", cliente: "", ciudad: "", fecha_inicio: "2026-12-01", fecha_fin: "2026-12-02", moneda: "USD" };
    const creado = await proyectos.crear(datos);
    expect(creado.id).toBe(9);
    const [ruta, init] = fetchFalso.mock.calls[0]!;
    expect(ruta).toBe("/api/v1/proyectos");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(datos);
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("token-csrf");
  });

  it("editar va a la dirección del proyecto", async () => {
    const { fetchFalso, proyectos } = preparar(respuestaJson(proyectoDePrueba({ id: 3 })));
    await proyectos.editar(3, { nombre: "Torre", cliente: "", ciudad: "", fecha_inicio: "2026-12-01", fecha_fin: "2026-12-02", moneda: "USD" });
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/proyectos/3");
  });

  it("un 422 trae el campo que hay que corregir", async () => {
    const { proyectos } = preparar(
      respuestaJson(
        { error: { code: "VALIDATION_ERROR", message: "Hay datos que no son válidos.", fields: { fecha_fin: "La fecha final no puede ser anterior a la inicial." } }, request_id: "r1" },
        422,
      ),
    );
    const error = await errorDe(
      proyectos.crear({ nombre: "Torre", cliente: "", ciudad: "", fecha_inicio: "2026-12-05", fecha_fin: "2026-12-02", moneda: "USD" }),
    );
    expect(error.tipo).toBe("validacion");
    expect(error.campos.fecha_fin).toBe("La fecha final no puede ser anterior a la inicial.");
  });

  it("403 es «sin permiso»", async () => {
    const { proyectos } = preparar(respuestaJson({ error: { code: "FORBIDDEN", message: "x" }, request_id: "r1" }, 403));
    expect((await errorDe(proyectos.listar({}))).tipo).toBe("prohibido");
  });

  it("las descargas son direcciones de la API: el CSV y el Excel contable del proyecto", () => {
    const { proyectos } = preparar();
    expect(proyectos.urlCsv(4)).toBe("/api/v1/proyectos/4/exportar.csv");
    expect(proyectos.urlLibroContable(4, { desde: "2026-11-01", hasta: "2026-11-30" })).toBe(
      "/api/v1/gastos/contable?desde=2026-11-01&hasta=2026-11-30&proyecto_id=4",
    );
  });
});
