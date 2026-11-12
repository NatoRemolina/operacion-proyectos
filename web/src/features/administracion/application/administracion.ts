"use client";

import { useQuery } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import type { AdministracionRepository } from "../domain/administracion";

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
