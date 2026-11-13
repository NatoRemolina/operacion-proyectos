import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import type { TramoVuelo, VuelosRepository } from "../domain/vuelos";

/**
 * Vuelos en memoria para pruebas y para el modo demostración. Sin tramos (`null`) se comporta como la API con
 * alguien que no es de administración: «prohibido». «Actualizar» no consulta nada: responde con lo que hay.
 */
export function crearVuelosMemoria(opciones: {
  tramos?: TramoVuelo[] | null;
  hoy?: string;
  sesion?: SesionMemoria;
  latenciaMs?: number;
} = {}): VuelosRepository {
  const { sesion, latenciaMs = 0, hoy = "2026-12-13" } = opciones;
  return {
    async delDia(fecha, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.tramos) throw new ErrorDeAplicacion("prohibido");
      return { fecha, hoy, tramos: opciones.tramos.filter((t) => t.fecha === (fecha ?? hoy)) };
    },
    async actualizar(tramoId) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      if (!opciones.tramos) throw new ErrorDeAplicacion("prohibido");
      const tramo = opciones.tramos.find((t) => t.id === tramoId);
      if (!tramo) throw new ErrorDeAplicacion("no_encontrado");
      return { consultado: false, motivo: "consultado hace menos de 1 min", mensaje: `${tramo.numero}: no se consultó (consultado hace menos de 1 min).`, tramo };
    },
  };
}
