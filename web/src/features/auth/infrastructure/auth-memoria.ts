import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { AuthRepository, Persona } from "../domain/auth";

export interface CuentaMemoria {
  readonly persona: Persona;
  readonly clave: string;
}

/** Autenticación en memoria para pruebas y para el modo demostración. */
export function crearAuthMemoria(opciones: {
  cuentas: readonly CuentaMemoria[];
  sesion: SesionMemoria;
  latenciaMs?: number;
}): AuthRepository {
  const { cuentas, sesion, latenciaMs = 0 } = opciones;
  return {
    async entrar(correo, clave) {
      await esperar(latenciaMs);
      const cuenta = cuentas.find(
        (c) => c.persona.correo.toLowerCase() === correo.trim().toLowerCase() && c.clave === clave,
      );
      if (!cuenta) throw new ErrorDeAplicacion("credenciales");
      sesion.abrir(cuenta.persona.id);
      return cuenta.persona;
    },
    async quienSoy() {
      await esperar(latenciaMs);
      const id = sesion.personaId();
      return cuentas.find((c) => c.persona.id === id)?.persona ?? null;
    },
    async salir() {
      await esperar(latenciaMs);
      sesion.cerrar();
    },
  };
}
