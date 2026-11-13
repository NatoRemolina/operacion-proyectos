"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import type { CuentaRepository, MiCuenta, VinculoTelegram } from "../domain/cuenta";

const contexto = crearContextoRepositorio<CuentaRepository>("CuentaRepository");
export const CuentaRepositoryProvider = contexto.Proveedor;
export const useCuentaRepository = contexto.useRepositorio;

function useClave() {
  return claveDePersona(usePersonaId(), "cuenta");
}

export function useMiCuenta() {
  const repositorio = useCuentaRepository();
  const clave = useClave();
  const consulta = useQuery({ queryKey: clave, queryFn: ({ signal }) => repositorio.obtener(signal) });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

function conError<T, V>(accion: (variables: V) => Promise<T>) {
  return async (variables: V) => {
    try {
      return await accion(variables);
    } catch (error) {
      throw comoErrorDeAplicacion(error);
    }
  };
}

/** Al terminar bien se olvida lo enviado: las contraseñas no quedan en el estado ni en la caché de la acción. */
export function useOlvidarAlTerminar(mutacion: { isSuccess: boolean; reset: () => void }) {
  const { isSuccess, reset } = mutacion;
  useEffect(() => {
    if (isSuccess) reset();
  }, [isSuccess, reset]);
}

export function useCambiarMiClave() {
  const repositorio = useCuentaRepository();
  const mutacion = useMutation<{ mensaje: string }, ErrorDeAplicacion, { actual: string; nueva: string }>({
    mutationFn: conError(({ actual, nueva }) => repositorio.cambiarClave(actual, nueva)),
    gcTime: 0,
  });
  useOlvidarAlTerminar(mutacion);
  return mutacion;
}

export function useVincularTelegram() {
  const repositorio = useCuentaRepository();
  return useMutation<VinculoTelegram, ErrorDeAplicacion, void>({ mutationFn: conError(() => repositorio.vincularTelegram()) });
}

export function useDesvincularTelegram() {
  const repositorio = useCuentaRepository();
  const queryClient = useQueryClient();
  const clave = useClave();
  return useMutation<MiCuenta, ErrorDeAplicacion, void>({
    mutationFn: conError(() => repositorio.desvincularTelegram()),
    onSuccess: (cuenta) => queryClient.setQueryData(clave, cuenta),
  });
}
