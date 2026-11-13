"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import { useOlvidarAlTerminar } from "@/features/cuenta/application/cuenta";
import type { Cargo, ResultadoUsuario, UsuariosRepository } from "../domain/usuarios";

const contexto = crearContextoRepositorio<UsuariosRepository>("UsuariosRepository");
export const UsuariosRepositoryProvider = contexto.Proveedor;
export const useUsuariosRepository = contexto.useRepositorio;

export function useUsuarios() {
  const repositorio = useUsuariosRepository();
  const personaId = usePersonaId();
  const consulta = useInfiniteQuery({
    queryKey: claveDePersona(personaId, "usuarios", "lista"),
    queryFn: ({ pageParam, signal }) => repositorio.listar({ limite: 100, cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (pagina) => pagina.siguiente,
  });
  return {
    ...consulta,
    error: consulta.error as ErrorDeAplicacion | null,
    usuarios: consulta.data?.pages.flatMap((p) => p.items) ?? [],
  };
}

export function useCargos() {
  const repositorio = useUsuariosRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "usuarios", "cargos"),
    queryFn: ({ signal }) => repositorio.listarCargos(signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

/** Cuentas y cargos se leen juntos (la lista muestra el cargo; el catálogo cuenta personas): tras un cambio, se piden ambos. */
function useRefrescar() {
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "usuarios") });
}

/**
 * Caso de uso genérico sobre una cuenta: alta, permiso, cargo, proyectos, estado o contraseña. Al terminar bien se
 * olvida lo enviado (la contraseña inicial o la restablecida no quedan en el estado de la acción).
 */
export function useAccionCuenta<V>(accion: (repositorio: UsuariosRepository, variables: V) => Promise<ResultadoUsuario>) {
  const repositorio = useUsuariosRepository();
  const refrescar = useRefrescar();
  const mutacion = useMutation<ResultadoUsuario, ErrorDeAplicacion, V>({
    mutationFn: async (variables) => {
      try {
        return await accion(repositorio, variables);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: refrescar,
    gcTime: 0,
  });
  useOlvidarAlTerminar(mutacion);
  return mutacion;
}

export function useAccionCargo<V>(accion: (repositorio: UsuariosRepository, variables: V) => Promise<Cargo>) {
  const repositorio = useUsuariosRepository();
  const refrescar = useRefrescar();
  return useMutation<Cargo, ErrorDeAplicacion, V>({
    mutationFn: async (variables) => {
      try {
        return await accion(repositorio, variables);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: refrescar,
  });
}
