import { z } from "zod";
import { esErrorDeAplicacion } from "@/shared/domain/errores";
import type { ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { AuthRepository, Persona } from "../domain/auth";

export const personaSchema = z.object({
  id: z.number().int().positive(),
  codigo: z.string(),
  nombre: z.string(),
  rol: z.enum(["colaborador", "gestor", "admin"]),
  correo: z.string(),
  cargo: z.string().nullable(),
});

const sesionSchema = z.object({
  persona: personaSchema,
  csrf_token: z.string().min(1),
  demostracion: z.boolean().default(false),
});

export function crearAuthHttp(cliente: ClienteHttp): AuthRepository {
  return {
    async entrar(correo, clave): Promise<Persona> {
      const sesion = await cliente.postJson(
        "/auth/login",
        { correo, clave },
        sesionSchema,
        { csrf: false },
      );
      cliente.fijarCsrf(sesion.csrf_token);
      return { ...sesion.persona, demostracion: sesion.demostracion };
    },
    async quienSoy(signal) {
      try {
        const sesion = await cliente.get("/auth/me", sesionSchema, { signal });
        cliente.fijarCsrf(sesion.csrf_token);
        return { ...sesion.persona, demostracion: sesion.demostracion };
      } catch (error) {
        if (esErrorDeAplicacion(error) && error.tipo === "sesion_vencida") {
          cliente.fijarCsrf(null);
          return null;
        }
        throw error;
      }
    },
    async salir() {
      try {
        await cliente.postSinRespuesta("/auth/logout");
      } catch (error) {
        // Si la sesión ya no existía en el servidor, salir igual se cumplió.
        if (!(esErrorDeAplicacion(error) && error.tipo === "sesion_vencida")) throw error;
      } finally {
        cliente.fijarCsrf(null);
      }
    },
  };
}
