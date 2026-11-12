import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, paginar, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { ViajeResumen, ViajesRepository } from "../domain/viajes";

/** Viajes en memoria para pruebas y para el modo demostración. */
export function crearViajesMemoria(opciones: {
  viajes: readonly ViajeResumen[];
  sesion?: SesionMemoria;
  latenciaMs?: number;
}): ViajesRepository {
  const { viajes, sesion, latenciaMs = 0 } = opciones;
  return {
    async listar(filtro, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const visibles = viajes
        .filter((v) => !filtro.estado || v.estado === filtro.estado)
        .toSorted((a, b) => b.ida.localeCompare(a.ida));
      return paginar(visibles, filtro.limite, filtro.cursor);
    },
    async obtener(id, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const viaje = viajes.find((v) => v.id === id);
      if (!viaje) throw new ErrorDeAplicacion("no_encontrado");
      return { presupuesto_detalle: [], motivo: null, aprobado_en: null, ...viaje };
    },
  };
}
