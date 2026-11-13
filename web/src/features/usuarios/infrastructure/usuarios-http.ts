import { z } from "zod";
import { consulta, paginaSchema, type ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { Cargo, ResultadoUsuario, Usuario, UsuariosRepository } from "../domain/usuarios";

const referencia = z.object({ id: z.number().int(), nombre: z.string() });

export const usuarioSchema = z.object({
  id: z.number().int().positive(),
  codigo: z.string(),
  correo: z.string(),
  nombre: z.string(),
  rol: z.enum(["colaborador", "gestor", "admin"]),
  rol_texto: z.string(),
  cargo: referencia.nullable(),
  proyectos: z.array(referencia),
  activo: z.boolean(),
  telegram: z.object({ vinculado: z.boolean(), usuario: z.string().nullable() }),
  ultima_sesion: z.string().nullable(),
  creado: z.string().nullable(),
}) satisfies z.ZodType<Usuario>;

const resultadoSchema = z.object({ usuario: usuarioSchema, mensaje: z.string() }) satisfies z.ZodType<ResultadoUsuario>;

const cargoSchema = z.object({
  id: z.number().int().positive(),
  nombre: z.string(),
  activo: z.boolean(),
  personas: z.number().int().nonnegative(),
}) satisfies z.ZodType<Cargo>;

const listaSchema = paginaSchema(usuarioSchema);
const cargosSchema = z.object({ items: z.array(cargoSchema) });

export function crearUsuariosHttp(cliente: ClienteHttp): UsuariosRepository {
  const cambio = (id: number, que: string, cuerpo: unknown) =>
    cliente.postJson(`/usuarios/${encodeURIComponent(id)}/${que}`, cuerpo, resultadoSchema);
  return {
    listar(opciones, signal) {
      return cliente.get(`/usuarios${consulta({ limite: opciones.limite, cursor: opciones.cursor })}`, listaSchema, { signal });
    },
    crear(datos) {
      return cliente.postJson("/usuarios", datos, resultadoSchema);
    },
    cambiarRol: (id, rol) => cambio(id, "rol", { rol }),
    cambiarEstado: (id, activo) => cambio(id, "estado", { activo }),
    cambiarCargo: (id, cargoId) => cambio(id, "cargo", { cargo_id: cargoId }),
    asignarProyectos: (id, proyectosIds) => cambio(id, "proyectos", { proyectos_ids: proyectosIds }),
    restablecerClave: (id, clave) => cambio(id, "clave", { clave }),
    async listarCargos(signal) {
      return (await cliente.get("/cargos", cargosSchema, { signal })).items;
    },
    crearCargo(nombre) {
      return cliente.postJson("/cargos", { nombre }, cargoSchema);
    },
    cambiarCargoCatalogo(id, cambioCargo) {
      return cliente.postJson(`/cargos/${encodeURIComponent(id)}`, cambioCargo, cargoSchema);
    },
  };
}
