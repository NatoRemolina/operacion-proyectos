import { afterEach, describe, expect, it, vi } from "vitest";
import { crearAuthHttp } from "@/features/auth/infrastructure/auth-http";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { gastoDePrueba } from "@/test/fabricas";
import { crearGastosHttp } from "./gastos-http";

function respuestaJson(cuerpo: unknown, estado = 200, cabeceras: Record<string, string> = {}) {
  return new Response(JSON.stringify(cuerpo), {
    status: estado,
    headers: { "Content-Type": "application/json", "X-Peticion": "peticion-1", ...cabeceras },
  });
}

function errorApi(estado: number, code: string) {
  return respuestaJson({ error: { code, message: "x" }, request_id: "abc123" }, estado);
}

function preparar(...respuestas: Response[]) {
  const fetchFalso = vi.fn<typeof fetch>();
  for (const r of respuestas) fetchFalso.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fetchFalso);
  const cliente = crearClienteHttp("/api/v1");
  return { fetchFalso, cliente, gastos: crearGastosHttp(cliente), auth: crearAuthHttp(cliente) };
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

describe("adaptador HTTP de gastos", () => {
  it("200: lista validada, con cookie de sesión y sin caché", async () => {
    const { fetchFalso, gastos } = preparar(
      respuestaJson({ items: [gastoDePrueba()], siguiente: "c2" }),
    );

    const pagina = await gastos.listar({ limite: 20, viajeId: 7 });

    expect(pagina.items[0]?.comercio).toBe("Comercio de prueba");
    expect(pagina.items[0]?.total).toBe("54.00");
    expect(pagina.siguiente).toBe("c2");
    const [url, init] = fetchFalso.mock.calls[0]!;
    expect(url).toBe("/api/v1/gastos?viaje_id=7&limite=20");
    expect(init?.credentials).toBe("include");
    expect(init?.cache).toBe("no-store");
  });

  it("401: se traduce a sesión vencida", async () => {
    const { gastos } = preparar(errorApi(401, "UNAUTHENTICATED"));
    const error = await errorDe(gastos.listar({}));
    expect(error.tipo).toBe("sesion_vencida");
    expect(error.idPeticion).toBe("abc123");
  });

  it("404: lo ajeno y lo inexistente se ven igual", async () => {
    const { gastos } = preparar(errorApi(404, "NOT_FOUND"));
    const error = await errorDe(gastos.obtener(999));
    expect(error.tipo).toBe("no_encontrado");
  });

  it("JSON inválido: un cuerpo que no es JSON es un error de contrato", async () => {
    const { gastos } = preparar(
      new Response("<html>gateway</html>", { status: 200, headers: { "Content-Type": "text/html" } }),
    );
    const error = await errorDe(gastos.listar({}));
    expect(error.tipo).toBe("contrato");
  });

  it("JSON con otra forma: dinero como número se rechaza", async () => {
    const { gastos } = preparar(
      respuestaJson({ items: [{ ...gastoDePrueba(), total: 54 }], siguiente: null }),
    );
    const error = await errorDe(gastos.listar({}));
    expect(error.tipo).toBe("contrato");
  });

  it("error sin JSON se clasifica por su estado", async () => {
    const { gastos } = preparar(new Response("Bad gateway", { status: 502 }));
    const error = await errorDe(gastos.listar({}));
    expect(error.tipo).toBe("servidor");
  });

  it("fallo de red se traduce a error de red", async () => {
    const fetchFalso = vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchFalso);
    const gastos = crearGastosHttp(crearClienteHttp("/api/v1"));
    const error = await errorDe(gastos.listar({}));
    expect(error.tipo).toBe("red");
  });

  it("enviar: multipart con X-CSRF-Token del login e Idempotency-Key", async () => {
    const { fetchFalso, gastos, auth } = preparar(
      respuestaJson({
        persona: { id: 1, codigo: "P-1", nombre: "Ana", rol: "colaborador", correo: "a@b.co", cargo: null },
        csrf_token: "token-csrf",
      }),
      respuestaJson(gastoDePrueba({ estado: "aprobado_auto", estado_texto: "Aprobado" }), 201),
    );
    await auth.entrar("a@b.co", "clave");

    const archivo = new File(["contenido"], "recibo.jpg", { type: "image/jpeg" });
    const gasto = await gastos.enviar({ archivo, viajeId: 7, claveIdempotencia: "clave-1" });

    expect(gasto.estado).toBe("aprobado_auto");
    const [loginUrl, loginInit] = fetchFalso.mock.calls[0]!;
    expect(loginUrl).toBe("/api/v1/auth/login");
    expect(new Headers(loginInit?.headers).has("X-CSRF-Token")).toBe(false);

    const [url, init] = fetchFalso.mock.calls[1]!;
    expect(url).toBe("/api/v1/gastos");
    expect(init?.method).toBe("POST");
    const cabeceras = new Headers(init?.headers);
    expect(cabeceras.get("X-CSRF-Token")).toBe("token-csrf");
    expect(cabeceras.get("Idempotency-Key")).toBe("clave-1");
    expect(cabeceras.has("Content-Type")).toBe(false);
    const cuerpo = init?.body as FormData;
    expect((cuerpo.get("archivo") as File).name).toBe("recibo.jpg");
    expect(cuerpo.get("viaje_id")).toBe("7");
  });

  it("enviar en automático no manda viaje_id; 413 se traduce a archivo demasiado grande", async () => {
    const { fetchFalso, gastos } = preparar(errorApi(413, "PAYLOAD_TOO_LARGE"));
    const archivo = new File(["x"], "recibo.pdf", { type: "application/pdf" });
    const error = await errorDe(gastos.enviar({ archivo, viajeId: null, claveIdempotencia: "k" }));
    expect(error.tipo).toBe("demasiado_grande");
    expect((fetchFalso.mock.calls[0]![1]?.body as FormData).has("viaje_id")).toBe(false);
  });

  it("enviar con justificación la manda limpia; vacía no se manda", async () => {
    const { fetchFalso, gastos } = preparar(
      respuestaJson(gastoDePrueba(), 201),
      respuestaJson(gastoDePrueba(), 201),
    );
    const archivo = new File(["x"], "recibo.jpg", { type: "image/jpeg" });
    await gastos.enviar({ archivo, viajeId: null, claveIdempotencia: "a", justificacion: "  Peaje   hacia el lago " });
    await gastos.enviar({ archivo, viajeId: null, claveIdempotencia: "b", justificacion: "   " });
    expect((fetchFalso.mock.calls[0]![1]?.body as FormData).get("justificacion")).toBe("Peaje hacia el lago");
    expect((fetchFalso.mock.calls[1]![1]?.body as FormData).has("justificacion")).toBe(false);
  });

  it("justificar: JSON al endpoint del gasto y valida las justificaciones de la respuesta", async () => {
    const respuesta = gastoDePrueba({
      justificaciones: [
        { id: 4, tipo: "texto", canal: "api", texto: "Cena del equipo", transcripcion: "no_aplica", creado: "2026-11-12T10:00:00Z" },
      ],
    });
    const { fetchFalso, gastos } = preparar(respuestaJson(respuesta, 201));
    const gasto = await gastos.justificar(123, " Cena  del equipo ");
    expect(gasto.justificaciones[0]?.texto).toBe("Cena del equipo");
    const [url, init] = fetchFalso.mock.calls[0]!;
    expect(url).toBe("/api/v1/gastos/123/justificaciones");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ texto: "Cena del equipo" });
  });

  it("justificar: 403 es «prohibido» y una respuesta sin justificaciones rompe el contrato", async () => {
    const { gastos } = preparar(
      errorApi(403, "FORBIDDEN"),
      respuestaJson({ ...gastoDePrueba(), justificaciones: undefined }, 201),
    );
    expect((await errorDe(gastos.justificar(123, "Lo justifico yo"))).tipo).toBe("prohibido");
    expect((await errorDe(gastos.justificar(123, "Otra vez"))).tipo).toBe("contrato");
  });

  it("la dirección del original apunta a la API", () => {
    const { gastos } = preparar();
    expect(gastos.urlOriginal(55)).toBe("/api/v1/documentos/55/contenido");
  });
});

describe("adaptador HTTP de sesión", () => {
  it("me con 401 significa «sin sesión», no un fallo", async () => {
    const { auth } = preparar(errorApi(401, "UNAUTHENTICATED"));
    await expect(auth.quienSoy()).resolves.toBeNull();
  });

  it("credenciales incorrectas se distinguen de la sesión vencida", async () => {
    const { auth } = preparar(errorApi(401, "INVALID_CREDENTIALS"));
    const error = await errorDe(auth.entrar("a@b.co", "mala"));
    expect(error.tipo).toBe("credenciales");
  });
});
