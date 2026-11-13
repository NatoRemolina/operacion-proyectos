"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { problemaDePeriodo, type PeriodoContable } from "@/features/gastos/domain/gastos";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import type { DatosProyecto, ProyectoResumen, ProyectosRepository, TableroProyecto } from "../domain/proyectos";

const contexto = crearContextoRepositorio<ProyectosRepository>("ProyectosRepository");
export const ProyectosRepositoryProvider = contexto.Proveedor;
export const useProyectosRepository = contexto.useRepositorio;

export function useProyectos() {
  const repositorio = useProyectosRepository();
  const personaId = usePersonaId();
  const consulta = useInfiniteQuery({
    queryKey: claveDePersona(personaId, "proyectos", "lista"),
    queryFn: ({ pageParam, signal }) => repositorio.listar({ limite: 50, cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (pagina) => pagina.siguiente,
  });
  return {
    ...consulta,
    error: consulta.error as ErrorDeAplicacion | null,
    proyectos: consulta.data?.pages.flatMap((p) => p.items) ?? [],
  };
}

export function useTableroProyecto(id: number) {
  const repositorio = useProyectosRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "proyectos", "tablero", id),
    queryFn: ({ signal }) => repositorio.obtener(id, signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

/** Tras crear o editar, la lista y el formulario de cotizar (que ofrece los proyectos) se vuelven a pedir. */
function useRefrescarProyectos() {
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "proyectos", "lista") });
    void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "cotizar", "formulario") });
  };
}

export function useCrearProyecto() {
  const repositorio = useProyectosRepository();
  const refrescar = useRefrescarProyectos();
  return useMutation<ProyectoResumen, ErrorDeAplicacion, DatosProyecto>({
    mutationFn: async (datos) => {
      try {
        return await repositorio.crear(datos);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: refrescar,
  });
}

export function useEditarProyecto(id: number) {
  const repositorio = useProyectosRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  const refrescar = useRefrescarProyectos();
  return useMutation<ProyectoResumen, ErrorDeAplicacion, DatosProyecto>({
    mutationFn: async (datos) => {
      try {
        return await repositorio.editar(id, datos);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: (proyecto) => {
      queryClient.setQueryData<TableroProyecto>(claveDePersona(personaId, "proyectos", "tablero", id), (actual) =>
        actual ? { ...actual, proyecto } : actual,
      );
      refrescar();
    },
  });
}

export function useUrlCsvProyecto(id: number): string | null {
  return useProyectosRepository().urlCsv(id);
}

/** `null` si el periodo no se puede descargar o no hay plataforma conectada. */
export function useUrlLibroContableProyecto(id: number, periodo: PeriodoContable): string | null {
  const repositorio = useProyectosRepository();
  return problemaDePeriodo(periodo) ? null : repositorio.urlLibroContable(id, periodo);
}
