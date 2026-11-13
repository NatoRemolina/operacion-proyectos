"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import type { AccionCompra, Compra, CompraDetalle, ComprasRepository, RegistroCompra } from "../domain/compras";

const contexto = crearContextoRepositorio<ComprasRepository>("ComprasRepository");
export const ComprasRepositoryProvider = contexto.Proveedor;
export const useComprasRepository = contexto.useRepositorio;

export function useCompras() {
  const repositorio = useComprasRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "compras"),
    queryFn: ({ signal }) => repositorio.lista(signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

export function useCompra(id: number | null) {
  const repositorio = useComprasRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "compras", id),
    queryFn: ({ signal }) => repositorio.detalle(id!, signal),
    enabled: id !== null,
    refetchInterval: 4 * 60_000,   // el enlace a la página oficial vence en 5 minutos
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

/** Después de cualquier cambio se vuelve a leer: la lista, el detalle y su versión. También tras un conflicto. */
function useRefrescar() {
  const queryClient = useQueryClient();
  const personaId = usePersonaId();
  return () => queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "compras") });
}

export function useCambiarEstado(compra: CompraDetalle) {
  const repositorio = useComprasRepository();
  const refrescar = useRefrescar();
  return useMutation<Compra, ErrorDeAplicacion, { accion: AccionCompra; motivo: string }>({
    mutationFn: async ({ accion, motivo }) => {
      try {
        return await repositorio.cambiarEstado(compra.id, accion, compra.version, motivo);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSettled: () => void refrescar(),
  });
}

export function useRegistrarCompra(compra: CompraDetalle) {
  const repositorio = useComprasRepository();
  const refrescar = useRefrescar();
  return useMutation<Compra, ErrorDeAplicacion, RegistroCompra>({
    mutationFn: async (registro) => {
      try {
        return await repositorio.registrar(compra.id, compra.version, registro);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSettled: () => void refrescar(),
  });
}

export function useAnalizarCompra(id: number) {
  const repositorio = useComprasRepository();
  const refrescar = useRefrescar();
  return useMutation<CompraDetalle["analisis"], ErrorDeAplicacion, void>({
    mutationFn: async () => {
      try {
        return await repositorio.analizar(id);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSettled: () => void refrescar(),
  });
}
