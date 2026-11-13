import { afterEach, describe, expect, it, vi } from "vitest";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { crearCuentaHttp } from "./cuenta-http";

const CUENTA = {
  persona: { id: 2, codigo: "P-0002", nombre: "Andrés Molina", rol: "colaborador", correo: "piloto@demo.local", cargo: "Pilotaje de dron" },
  rol_texto: "colaborador",
  telegram: { vinculado: false, usuario: null, canal_activo: false },
};

function respuestaJson(cuerpo: unknown, estado = 200) {
  return new Response(JSON.stringify(cuerpo), { status: estado, headers: { "Content-Type": "application/json" } });
}

function preparar(...respuestas: Response[]) {
  const fetchFalso = vi.fn<typeof fetch>();
  for (const r of respuestas) fetchFalso.mockResolvedValueOnce(r);
  vi.stubGlobal("fetch", fetchFalso);
  const cliente = crearClienteHttp("/api/v1");
  cliente.fijarCsrf("token-viejo");
  return { fetchFalso, cuenta: crearCuentaHttp(cliente) };
}

const csrfDe = (fetchFalso: ReturnType<typeof vi.fn<typeof fetch>>, i: number) =>
  new Headers(fetchFalso.mock.calls[i]![1]?.headers).get("X-CSRF-Token");

afterEach(() => vi.unstubAllGlobals());

describe("adaptador HTTP de mi cuenta", () => {
  it("lee mis datos con la forma del contrato", async () => {
    const { fetchFalso, cuenta } = preparar(respuestaJson(CUENTA));
    expect((await cuenta.obtener()).persona.codigo).toBe("P-0002");
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/cuenta");
  });

  it("cambiar la contraseña renueva el token CSRF para las escrituras siguientes", async () => {
    const { fetchFalso, cuenta } = preparar(
      respuestaJson({ csrf_token: "token-nuevo", mensaje: "Contraseña cambiada. Se cerraron tus otras sesiones." }),
      respuestaJson(CUENTA),
    );
    const r = await cuenta.cambiarClave("clave-actual-123", "clave-nueva-456789");
    expect(r.mensaje).toContain("Contraseña cambiada");
    expect(JSON.parse(String(fetchFalso.mock.calls[0]![1]?.body))).toEqual({ actual: "clave-actual-123", nueva: "clave-nueva-456789" });
    expect(csrfDe(fetchFalso, 0)).toBe("token-viejo");
    await cuenta.desvincularTelegram();
    expect(fetchFalso.mock.calls[1]![0]).toBe("/api/v1/cuenta/telegram/desvincular");
    expect(csrfDe(fetchFalso, 1)).toBe("token-nuevo");
  });

  it("pide el vínculo de Telegram", async () => {
    const { fetchFalso, cuenta } = preparar(respuestaJson({ codigo: "abc123", enlace: "https://t.me/bot?start=abc123", minutos: 15 }));
    expect((await cuenta.vincularTelegram()).minutos).toBe(15);
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/cuenta/telegram/vinculo");
  });
});
