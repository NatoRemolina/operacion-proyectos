import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { crearAsistenteHttp } from "./asistente-http";

const RESPUESTA = {
  texto: "Hay 2 gastos en revisión.",
  modo: "asesor",
  modo_texto: "Asesor con herramientas",
  fuentes: [{ tipo: "gasto", codigo: "gasto #4", destino: { tipo: "gasto", id: 4 } }, { tipo: "persona", codigo: "P-0002", destino: null }],
  herramientas: ["kpi"],
  duracion_ms: 7842,
  usadas: 3,
  tope: 40,
};

function respuestaJson(cuerpo: unknown, estado = 200) {
  return new Response(JSON.stringify(cuerpo), { status: estado, headers: { "Content-Type": "application/json" } });
}

function preparar(...respuestas: Response[]) {
  const fetchFalso = vi.fn<typeof fetch>();
  for (const r of respuestas) fetchFalso.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fetchFalso);
  const cliente = crearClienteHttp("/api/v1");
  cliente.fijarCsrf("token-csrf");
  return { fetchFalso, asistente: crearAsistenteHttp(cliente) };
}

afterEach(() => vi.unstubAllGlobals());

describe("adaptador HTTP del asistente", () => {
  it("pregunta con JSON y el token CSRF, y lee la respuesta del contrato", async () => {
    const { fetchFalso, asistente } = preparar(respuestaJson(RESPUESTA));
    const r = await asistente.preguntar("  ¿Hay gastos en revisión?  ");
    expect(r.modo).toBe("asesor");
    expect(r.fuentes[0]?.destino).toEqual({ tipo: "gasto", id: 4 });
    const [url, init] = fetchFalso.mock.calls[0]!;
    expect(url).toBe("/api/v1/asistente");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ pregunta: "¿Hay gastos en revisión?" });
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("token-csrf");
  });

  it("una respuesta con otra forma es un error de contrato", async () => {
    const { asistente } = preparar(respuestaJson({ ...RESPUESTA, modo: "otro" }));
    await expect(asistente.preguntar("¿Hola?")).rejects.toMatchObject({ tipo: "contrato" });
  });

  it("dicta enviando el audio como formulario y devuelve el texto", async () => {
    const { fetchFalso, asistente } = preparar(respuestaJson({ texto: "¿Cómo van los indicadores?" }));
    const texto = await asistente.transcribir(new Blob([new Uint8Array(8)], { type: "audio/wav" }));
    expect(texto).toBe("¿Cómo van los indicadores?");
    const [url, init] = fetchFalso.mock.calls[0]!;
    expect(url).toBe("/api/v1/asistente/voz");
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("audio")).toBeInstanceOf(Blob);
  });

  it("la voz no disponible llega como error del servidor", async () => {
    const { asistente } = preparar(
      respuestaJson({ error: { code: "SERVICE_UNAVAILABLE", message: "No está configurada." }, request_id: "x" }, 503),
    );
    const error = await asistente.transcribir(new Blob([])).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ErrorDeAplicacion);
    expect((error as ErrorDeAplicacion).tipo).toBe("servidor");
  });
});
