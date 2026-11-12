"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { esErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import type { AuthRepository, Persona } from "../domain/auth";

const contexto = crearContextoRepositorio<AuthRepository>("AuthRepository");
export const AuthRepositoryProvider = contexto.Proveedor;
export const useAuthRepository = contexto.useRepositorio;

const CLAVE_SESION = ["sesion"] as const;

export function useSesion() {
  const repositorio = useAuthRepository();
  return useQuery<Persona | null, ErrorDeAplicacion>({
    queryKey: CLAVE_SESION,
    queryFn: ({ signal }) => repositorio.quienSoy(signal),
    staleTime: 60_000,
  });
}

export function useEntrar() {
  const repositorio = useAuthRepository();
  const queryClient = useQueryClient();
  return useMutation<Persona, ErrorDeAplicacion, { correo: string; clave: string }>({
    mutationFn: ({ correo, clave }) => repositorio.entrar(correo, clave),
    onSuccess: (persona) => {
      // Caché nueva por sesión: nada de una persona anterior sobrevive al cambio.
      queryClient.clear();
      queryClient.setQueryData(CLAVE_SESION, persona);
    },
  });
}

export function useSalir() {
  const repositorio = useAuthRepository();
  const queryClient = useQueryClient();
  return useMutation<void, ErrorDeAplicacion, void>({
    mutationFn: () => repositorio.salir(),
    onSettled: () => {
      queryClient.clear();
      queryClient.setQueryData(CLAVE_SESION, null);
    },
  });
}

/**
 * Si cualquier lectura descubre que la sesión venció, la sesión pasa a «sin sesión» y la zona
 * privada lleva a entrar con la ruta de regreso. Las escrituras no: su pantalla avisa sin perder lo escrito.
 */
export function useVigilarSesionVencida() {
  const queryClient = useQueryClient();
  useEffect(
    () =>
      queryClient.getQueryCache().subscribe((evento) => {
        if (evento.type !== "updated" || evento.action.type !== "error") return;
        if (evento.query.queryKey[0] === CLAVE_SESION[0]) return;
        const error = evento.action.error;
        if (esErrorDeAplicacion(error) && error.tipo === "sesion_vencida") {
          queryClient.setQueryData(CLAVE_SESION, null);
        }
      }),
    [queryClient],
  );
}
