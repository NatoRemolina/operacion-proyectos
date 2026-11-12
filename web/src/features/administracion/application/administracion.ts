"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import { useGastosRepository } from "@/features/gastos/application/gastos";
import type { GastoDetalle, GastoResumen } from "@/features/gastos/domain/gastos";
import type {
  AdministracionRepository,
  CambioEstadoViaje,
  ResultadoCambioEstado,
  RevisionGasto,
} from "../domain/administracion";

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
    onError: (error) => {
      // Si el viaje ya cambió (otra persona lo decidió) lo que se ve está viejo: se vuelve a pedir.
      if (error.tipo === "estado_invalido") {
        void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "viajes") });
        void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "administracion") });
      }
    },
  });
}

/**
 * Caso de uso «revisar un gasto». Además del gasto revisado devuelve el siguiente en revisión, para
 * seguir con la bandeja sin volver a la lista. Si otra persona lo cambió, se recarga lo último.
 */
export function useRevisarGasto(id: number) {
  const repositorio = useAdministracionRepository();
  const gastos = useGastosRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  const claveDetalle = claveDePersona(personaId, "gastos", "detalle", id);
  return useMutation<{ gasto: GastoDetalle; siguiente: GastoResumen | null }, ErrorDeAplicacion, RevisionGasto>({
    mutationFn: async (revision) => {
      try {
        const gasto = await repositorio.revisarGasto(id, revision);
        // Se miran varios: si los primeros son propios, el siguiente ajeno puede venir más abajo.
        const pendientes = await gastos.listar({ estado: "revision", limite: 50 }).catch(() => null);
        // Lo propio no lo revisa quien revisa: el siguiente es el primero ajeno.
        return { gasto, siguiente: pendientes?.items.find((g) => g.id !== id && !g.propio) ?? null };
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: ({ gasto }) => {
      queryClient.setQueryData(claveDetalle, gasto);
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "gastos", "lista") });
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "viajes") });
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "administracion") });
    },
    onError: (error) => {
      if (error.tipo === "cambio_ajeno") void queryClient.invalidateQueries({ queryKey: claveDetalle });
    },
  });
}
