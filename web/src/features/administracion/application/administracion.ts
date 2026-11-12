"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import type { AdministracionRepository, CambioEstadoViaje, ResultadoCambioEstado } from "../domain/administracion";

const contexto = crearContextoRepositorio<AdministracionRepository>("AdministracionRepository");
export const AdministracionRepositoryProvider = contexto.Proveedor;
export const useAdministracionRepository = contexto.useRepositorio;

/** El resumen se refresca solo cada 30 s: es el tablero que administración deja abierto. */
export function useResumen() {
  const repositorio = useAdministracionRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "administracion", "resumen"),
    queryFn: ({ signal }) => repositorio.resumen(signal),
    refetchInterval: 30_000,
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

/**
 * Caso de uso «decidir un viaje» (aprobar, rechazar, reabrir, cerrar). Al terminar, el detalle del
 * viaje queda con lo que respondió el servidor y las listas y el resumen se vuelven a pedir.
 */
export function useCambiarEstadoViaje() {
  const repositorio = useAdministracionRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  return useMutation<ResultadoCambioEstado, ErrorDeAplicacion, { id: number; cambio: CambioEstadoViaje }>({
    mutationFn: async ({ id, cambio }) => {
      try {
        return await repositorio.cambiarEstadoViaje(id, cambio);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: ({ viaje }) => {
      queryClient.setQueryData(claveDePersona(personaId, "viajes", "detalle", viaje.id), viaje);
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "viajes") });
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "administracion") });
    },
  });
}
