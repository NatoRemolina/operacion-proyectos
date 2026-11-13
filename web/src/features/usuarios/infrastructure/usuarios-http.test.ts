import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { CARGOS_DE_PRUEBA, usuarioDePrueba } from "../test/fabricas";
import { crearUsuariosHttp } from "./usuarios-http";

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
  return { fetchFalso, usuarios: crearUsuariosHttp(cliente) };
}

function cuerpoDe(fetchFalso: ReturnType<typeof vi.fn<typeof fetch>>, i = 0) {
  const [ruta, init] = fetchFalso.mock.calls[i]!;
  expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("token-csrf");
  return { ruta, cuerpo: JSON.parse(String(init?.body)) };
}

afterEach(() => vi.unstubAllGlobals());

describe("adaptador HTTP de usuarios", () => {
  it("lista con la forma del contrato", async () => {
    const { fetchFalso, usuarios } = preparar(respuestaJson({ items: [usuarioDePrueba()], siguiente: null }));
    const pagina = await usuarios.listar({ limite: 100 });
    expect(pagina.items[0]?.proyectos[0]?.nombre).toBe("Residencial Summerlin (aéreo)");
    expect(fetchFalso.mock.calls[0]![0]).toBe("/api/v1/usuarios?limite=100");
  });

  it("crea una cuenta y la respuesta no trae la contraseña", async () => {
    const { fetchFalso, usuarios } = preparar(respuestaJson({ usuario: usuarioDePrueba({ id: 9 }), mensaje: "Cuenta creada." }, 201));
    const datos = { correo: "nueva@demo.local", nombre: "Nueva", rol: "colaborador" as const, clave: "clave-inicial-123", cargo_id: null };
    const r = await usuarios.crear(datos);
    expect(r.usuario.id).toBe(9);
    expect(JSON.stringify(r)).not.toContain("clave-inicial-123");
    expect(cuerpoDe(fetchFalso)).toEqual({ ruta: "/api/v1/usuarios", cuerpo: datos });
  });

  it("cada cambio va a su dirección con su cuerpo", async () => {
    const ok = () => respuestaJson({ usuario: usuarioDePrueba(), mensaje: "Hecho." });
    const { fetchFalso, usuarios } = preparar(ok(), ok(), ok(), ok(), ok());
    await usuarios.cambiarRol(4, "admin");
    await usuarios.cambiarEstado(4, false);
    await usuarios.cambiarCargo(4, null);
    await usuarios.asignarProyectos(4, [1, 2]);
    await usuarios.restablecerClave(4, "clave-nueva-456789");
    expect([0, 1, 2, 3, 4].map((i) => cuerpoDe(fetchFalso, i))).toEqual([
      { ruta: "/api/v1/usuarios/4/rol", cuerpo: { rol: "admin" } },
      { ruta: "/api/v1/usuarios/4/estado", cuerpo: { activo: false } },
      { ruta: "/api/v1/usuarios/4/cargo", cuerpo: { cargo_id: null } },
      { ruta: "/api/v1/usuarios/4/proyectos", cuerpo: { proyectos_ids: [1, 2] } },
      { ruta: "/api/v1/usuarios/4/clave", cuerpo: { clave: "clave-nueva-456789" } },
    ]);
  });

  it("una protección (409 INVALID_STATE) trae el motivo del servidor", async () => {
    const { usuarios } = preparar(
      respuestaJson({ error: { code: "INVALID_STATE", message: "No puedes desactivar tu propia cuenta ni al último administrador." }, request_id: "r1" }, 409),
    );
    const error = await usuarios.cambiarEstado(1, false).catch((e: unknown) => e as ErrorDeAplicacion);
    expect(error).toBeInstanceOf(ErrorDeAplicacion);
    expect((error as ErrorDeAplicacion).tipo).toBe("estado_invalido");
    expect((error as ErrorDeAplicacion).message).toBe("No puedes desactivar tu propia cuenta ni al último administrador.");
  });

  it("cargos: lista, crea y cambia", async () => {
    const { fetchFalso, usuarios } = preparar(
      respuestaJson({ items: CARGOS_DE_PRUEBA }),
      respuestaJson({ id: 9, nombre: "Logística", activo: true, personas: 0 }, 201),
      respuestaJson({ id: 9, nombre: "Logística", activo: false, personas: 0 }),
    );
    expect(await usuarios.listarCargos()).toHaveLength(4);
    expect((await usuarios.crearCargo("Logística")).id).toBe(9);
    expect((await usuarios.cambiarCargoCatalogo(9, { activo: false })).activo).toBe(false);
    expect(cuerpoDe(fetchFalso, 1)).toEqual({ ruta: "/api/v1/cargos", cuerpo: { nombre: "Logística" } });
    expect(cuerpoDe(fetchFalso, 2)).toEqual({ ruta: "/api/v1/cargos/9", cuerpo: { activo: false } });
  });
});
