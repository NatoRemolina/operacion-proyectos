"use client";

import { useQuery } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import type { FiltrosTablero, KpisRepository } from "../domain/kpis";

const contexto = crearContextoRepositorio<KpisRepository>("KpisRepository");
export const KpisRepositoryProvider = contexto.Proveedor;
export const useKpisRepository = contexto.useRepositorio;

export function useTableroKpis(filtros: FiltrosTablero) {
  const repositorio = useKpisRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "kpis", "tablero", filtros),
    queryFn: ({ signal }) => repositorio.tablero(filtros, signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

export function useFichaPersona(id: number) {
  const repositorio = useKpisRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "kpis", "ficha", id),
    queryFn: ({ signal }) => repositorio.ficha(id, signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}
