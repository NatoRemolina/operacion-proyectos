import { z } from "zod";
import { personaSchema } from "@/features/auth/infrastructure/auth-http";
import type { ClienteHttp } from "@/shared/infrastructure/cliente-http";
import type { CuentaRepository, MiCuenta, VinculoTelegram } from "../domain/cuenta";

const cuentaSchema = z.object({
  persona: personaSchema,
  rol_texto: z.string(),
  telegram: z.object({ vinculado: z.boolean(), usuario: z.string().nullable(), canal_activo: z.boolean() }),
}) satisfies z.ZodType<MiCuenta>;

const vinculoSchema = z.object({
  codigo: z.string().min(1),
  enlace: z.string().nullable(),
  minutos: z.number().int().positive(),
}) satisfies z.ZodType<VinculoTelegram>;

const claveSchema = z.object({ csrf_token: z.string().min(1), mensaje: z.string() });

export function crearCuentaHttp(cliente: ClienteHttp): CuentaRepository {
  return {
    obtener(signal) {
      return cliente.get("/cuenta", cuentaSchema, { signal });
    },
    async cambiarClave(actual, nueva) {
      const r = await cliente.postJson("/cuenta/clave", { actual, nueva }, claveSchema);
      // La sesión se renovó: el token anterior ya no sirve para escribir.
      cliente.fijarCsrf(r.csrf_token);
      return { mensaje: r.mensaje };
    },
    vincularTelegram() {
      return cliente.postJson("/cuenta/telegram/vinculo", {}, vinculoSchema);
    },
    desvincularTelegram() {
      return cliente.postJson("/cuenta/telegram/desvincular", {}, cuentaSchema);
    },
  };
}
