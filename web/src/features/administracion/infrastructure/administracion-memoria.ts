import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { AdministracionRepository, ResumenAdmin } from "../domain/administracion";

/**
 * Administración en memoria para pruebas y para el modo demostración. Sin resumen (`null` o sin
 * datos) se comporta como la API con alguien que no es de administración: «prohibido».
 */
export function crearAdministracionMemoria(opciones: {
  resumen?: ResumenAdmin | null;
  sesion?: SesionMemoria;
  latenciaMs?: number;
}): AdministracionRepository {
  const { sesion, latenciaMs = 0 } = opciones;
  return {
    async resumen(signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.resumen) throw new ErrorDeAplicacion("prohibido");
      return opciones.resumen;
    },
  };
}
