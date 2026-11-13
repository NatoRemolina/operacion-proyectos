import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import { CLAVE_ACTUAL, CLAVE_NUEVA, type CuentaRepository, type MiCuenta } from "../domain/cuenta";

/** La cuenta propia en memoria (pruebas y modo demostración), con las mismas reglas y mensajes que la API. */
export function crearCuentaMemoria(opciones: {
  cuenta: MiCuenta;
  clave: string;
  sesion?: SesionMemoria;
  latenciaMs?: number;
}): CuentaRepository {
  const { sesion, latenciaMs = 0 } = opciones;
  let cuenta = opciones.cuenta;
  let clave = opciones.clave;

  async function preparar(signal?: AbortSignal) {
    await esperar(latenciaMs, signal);
    exigirSesion(sesion);
  }

  return {
    async obtener(signal) {
      await preparar(signal);
      return cuenta;
    },
    async cambiarClave(actual, nueva) {
      await preparar();
      if (actual !== clave) throw new ErrorDeAplicacion("validacion", { campos: { actual: CLAVE_ACTUAL } });
      if (nueva.length < 10 || nueva === actual) throw new ErrorDeAplicacion("validacion", { campos: { nueva: CLAVE_NUEVA } });
      clave = nueva;
      return { mensaje: "Contraseña cambiada. Se cerraron tus otras sesiones." };
    },
    async vincularTelegram() {
      await preparar();
      if (!cuenta.telegram.canal_activo) {
        throw new ErrorDeAplicacion("estado_invalido", {
          mensaje: "El canal de Telegram no está configurado en esta instalación. Los gastos entran por la plataforma.",
        });
      }
      const codigo = Math.random().toString(36).slice(2, 14);
      return { codigo, enlace: `https://t.me/bot_de_demostracion?start=${codigo}`, minutos: 15 };
    },
    async desvincularTelegram() {
      await preparar();
      cuenta = { ...cuenta, telegram: { ...cuenta.telegram, vinculado: false, usuario: null } };
      return cuenta;
    },
  };
}
