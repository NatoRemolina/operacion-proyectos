import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { MonitoreoRepository, Pestana, PestanaMonitoreo } from "../domain/monitoreo";

/**
 * Monitoreo en memoria para pruebas y para el modo demostración. Sin pestañas se comporta como la API
 * con alguien que no es de administración: «prohibido». No exporta.
 */
export function crearMonitoreoMemoria(opciones: {
  pestanas?: Partial<Record<Pestana, PestanaMonitoreo>> | null;
  sesion?: SesionMemoria;
  latenciaMs?: number;
} = {}): MonitoreoRepository {
  const { sesion, latenciaMs = 0 } = opciones;
  return {
    async pestana(p, filtros, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.pestanas) throw new ErrorDeAplicacion("prohibido");
      const datos = opciones.pestanas[p];
      if (!datos) throw new ErrorDeAplicacion("no_encontrado");
      return { ...datos, filtros };
    },
    urlExportar() {
      return null;
    },
  };
}
