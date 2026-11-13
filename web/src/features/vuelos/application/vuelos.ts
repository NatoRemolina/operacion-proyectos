"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import { REFRESCO_MS, type ResultadoActualizacion, type VuelosRepository } from "../domain/vuelos";

const contexto = crearContextoRepositorio<VuelosRepository>("VuelosRepository");
export const VuelosRepositoryProvider = contexto.Proveedor;
export const useVuelosRepository = contexto.useRepositorio;

/**
 * Los tramos del día, pedidos de nuevo cada 15 s. Con la pestaña oculta no se piden (TanStack no refresca
 * en segundo plano), así una pestaña olvidada no gasta consultas del plan.
 */
export function useVuelosDelDia(fecha: string | null) {
  const repositorio = useVuelosRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "vuelos", fecha ?? "hoy"),
    queryFn: ({ signal }) => repositorio.delDia(fecha, signal),
    refetchInterval: REFRESCO_MS,
    refetchIntervalInBackground: false,
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

export function useActualizarVuelo() {
  const repositorio = useVuelosRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  return useMutation<ResultadoActualizacion, ErrorDeAplicacion, number>({
    mutationFn: async (tramoId) => {
      try {
        return await repositorio.actualizar(tramoId);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "vuelos") }),
  });
}
