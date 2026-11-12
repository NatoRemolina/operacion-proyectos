"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { viajesParaRecibo, type FiltroViajes, type ViajesRepository } from "../domain/viajes";

const contexto = crearContextoRepositorio<ViajesRepository>("ViajesRepository");
export const ViajesRepositoryProvider = contexto.Proveedor;
export const useViajesRepository = contexto.useRepositorio;

export function useViajes(filtro: Omit<FiltroViajes, "cursor"> = {}) {
  const repositorio = useViajesRepository();
  const personaId = usePersonaId();
  const consulta = useInfiniteQuery({
    queryKey: claveDePersona(personaId, "viajes", filtro),
    queryFn: ({ pageParam, signal }) =>
      repositorio.listar({ limite: 20, ...filtro, cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (pagina) => pagina.siguiente,
  });
  return {
    ...consulta,
    error: consulta.error as ErrorDeAplicacion | null,
    viajes: consulta.data?.pages.flatMap((p) => p.items) ?? [],
  };
}

/** Opciones del selector de viaje al enviar un recibo. */
export function useViajesParaRecibo() {
  const repositorio = useViajesRepository();
  const personaId = usePersonaId();
  return useQuery({
    queryKey: claveDePersona(personaId, "viajes", "para-recibo"),
    queryFn: async ({ signal }) => {
      const pagina = await repositorio.listar({ estado: "aprobado", limite: 100 }, signal);
      return viajesParaRecibo(pagina.items, personaId);
    },
  });
}
