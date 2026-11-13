"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAdministracionRepository } from "@/features/administracion/application/administracion";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import type { CatalogoReglas, Regla, ReglasRepository } from "../domain/reglas";

/** Las reglas son de administración: viajan por el mismo puerto (y el mismo cliente con su token). */
function useReglasRepository(): ReglasRepository {
  return useAdministracionRepository();
}

export function useCatalogoReglas() {
  const repositorio = useReglasRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "reglas"),
    queryFn: ({ signal }) => repositorio.catalogoReglas(signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

/** Caso de uso «editar una regla». El catálogo queda con lo que respondió el servidor. */
export function useEditarRegla() {
  const repositorio = useReglasRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  return useMutation<Regla, ErrorDeAplicacion, { id: number; valor: string }>({
    mutationFn: async ({ id, valor }) => {
      try {
        return await repositorio.editarRegla(id, valor);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: (regla) => {
      queryClient.setQueryData<CatalogoReglas>(claveDePersona(personaId, "reglas"), (catalogo) =>
        catalogo
          ? { ...catalogo, grupos: catalogo.grupos.map((g) => ({ ...g, reglas: g.reglas.map((r) => (r.id === regla.id ? regla : r)) })) }
          : catalogo,
      );
    },
  });
}
