import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { FichaPersona, KpisRepository, TableroKpis } from "../domain/kpis";

/**
 * KPIs en memoria para pruebas y para el modo demostración. Sin tablero se comporta como la API con
 * alguien que no es de administración: «prohibido». No exporta: el CSV lo arma el servidor.
 */
export function crearKpisMemoria(opciones: {
  tablero?: TableroKpis | null;
  fichas?: readonly FichaPersona[];
  sesion?: SesionMemoria;
  latenciaMs?: number;
} = {}): KpisRepository {
  const { sesion, latenciaMs = 0 } = opciones;
  return {
    async tablero(filtros, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.tablero) throw new ErrorDeAplicacion("prohibido");
      return { ...opciones.tablero, filtros };
    },
    async ficha(id, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.tablero) throw new ErrorDeAplicacion("prohibido");
      const ficha = (opciones.fichas ?? []).find((f) => f.usuario.id === id);
      if (!ficha) throw new ErrorDeAplicacion("no_encontrado");
      return ficha;
    },
    urlExportar() {
      return null;
    },
  };
}
