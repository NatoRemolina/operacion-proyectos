"use client";

import { useQuery } from "@tanstack/react-query";
import type { FiltrosTablero } from "@/features/kpis/domain/kpis";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import type { MonitoreoRepository, Pestana } from "../domain/monitoreo";

const contexto = crearContextoRepositorio<MonitoreoRepository>("MonitoreoRepository");
export const MonitoreoRepositoryProvider = contexto.Proveedor;
export const useMonitoreoRepository = contexto.useRepositorio;

export function usePestanaMonitoreo(pestana: Pestana, filtros: FiltrosTablero) {
  const repositorio = useMonitoreoRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "monitoreo", pestana, filtros),
    queryFn: ({ signal }) => repositorio.pestana(pestana, filtros, signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}
