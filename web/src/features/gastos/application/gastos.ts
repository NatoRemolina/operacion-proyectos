"use client";

import { useCallback, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { nuevaClaveIdempotencia } from "@/shared/application/clave-idempotencia";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { ErrorDeAplicacion, comoErrorDeAplicacion } from "@/shared/domain/errores";
import {
  problemaDeJustificacion,
  validarArchivo,
  type FiltroGastos,
  type GastoDetalle,
  type GastosRepository,
} from "../domain/gastos";

const contexto = crearContextoRepositorio<GastosRepository>("GastosRepository");
export const GastosRepositoryProvider = contexto.Proveedor;
export const useGastosRepository = contexto.useRepositorio;

export function useGastos(filtro: Omit<FiltroGastos, "cursor"> = {}) {
  const repositorio = useGastosRepository();
  const personaId = usePersonaId();
  const consulta = useInfiniteQuery({
    queryKey: claveDePersona(personaId, "gastos", "lista", filtro),
    queryFn: ({ pageParam, signal }) =>
      repositorio.listar({ limite: 20, ...filtro, cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (pagina) => pagina.siguiente,
  });
  return {
    ...consulta,
    error: consulta.error as ErrorDeAplicacion | null,
    gastos: consulta.data?.pages.flatMap((p) => p.items) ?? [],
  };
}

export function useGasto(id: number) {
  const repositorio = useGastosRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "gastos", "detalle", id),
    queryFn: ({ signal }) => repositorio.obtener(id, signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

export function useUrlOriginal(documentoId: number | null): string | null {
  const repositorio = useGastosRepository();
  return documentoId === null ? null : repositorio.urlOriginal(documentoId);
}

/**
 * Caso de uso «enviar un recibo». Cada archivo elegido recibe su propia clave de idempotencia;
 * reintentar reutiliza la misma, así un doble envío o un corte de red no crean dos gastos.
 */
export function useEnvioRecibo() {
  const repositorio = useGastosRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  const [seleccion, setSeleccion] = useState<{ archivo: File; clave: string } | null>(null);
  const [errorPrevio, setErrorPrevio] = useState<ErrorDeAplicacion | null>(null);

  const mutacion = useMutation<
    GastoDetalle,
    ErrorDeAplicacion,
    { archivo: File; clave: string; viajeId: number | null; justificacion: string }
  >({
    mutationFn: async ({ archivo, clave, viajeId, justificacion }) => {
      try {
        return await repositorio.enviar({ archivo, viajeId, claveIdempotencia: clave, justificacion });
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: (gasto) => {
      queryClient.setQueryData(claveDePersona(personaId, "gastos", "detalle", gasto.id), gasto);
      // La lista de gastos y la ejecución de los viajes cambian con el nuevo gasto.
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "gastos", "lista") });
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "viajes") });
    },
  });
  const { reset, mutate, isPending } = mutacion;

  const elegirArchivo = useCallback(
    (archivo: File | null) => {
      reset();
      setErrorPrevio(null);
      if (!archivo) {
        setSeleccion(null);
        return;
      }
      const invalido = validarArchivo(archivo);
      if (invalido) setErrorPrevio(new ErrorDeAplicacion(invalido));
      setSeleccion({ archivo, clave: nuevaClaveIdempotencia() });
    },
    [reset],
  );

  const enviar = useCallback(
    (viajeId: number | null, justificacion = "") => {
      if (!seleccion || isPending) return;
      const invalido = validarArchivo(seleccion.archivo);
      if (invalido) {
        setErrorPrevio(new ErrorDeAplicacion(invalido));
        return;
      }
      setErrorPrevio(null);
      mutate({ ...seleccion, viajeId, justificacion });
    },
    [seleccion, isPending, mutate],
  );

  const reiniciar = useCallback(() => {
    reset();
    setErrorPrevio(null);
    setSeleccion(null);
  }, [reset]);

  return {
    archivo: seleccion?.archivo ?? null,
    claveIdempotencia: seleccion?.clave ?? null,
    elegirArchivo,
    enviar,
    reiniciar,
    enviando: isPending,
    resultado: mutacion.data ?? null,
    error: errorPrevio ?? mutacion.error ?? null,
  };
}

/**
 * Caso de uso «justificar un gasto»: la persona cuenta para qué fue. La regla de longitud se revisa
 * antes de llamar al servidor, que la vuelve a aplicar.
 */
export function useJustificacion(id: number) {
  const repositorio = useGastosRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  const [errorPrevio, setErrorPrevio] = useState<string | null>(null);
  const mutacion = useMutation<GastoDetalle, ErrorDeAplicacion, string>({
    mutationFn: async (texto) => {
      try {
        return await repositorio.justificar(id, texto);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: (gasto) => {
      queryClient.setQueryData(claveDePersona(personaId, "gastos", "detalle", gasto.id), gasto);
    },
  });
  const { mutate, reset, isPending } = mutacion;

  const justificar = useCallback(
    (texto: string, alTerminar?: () => void) => {
      if (isPending) return;
      const problema = problemaDeJustificacion(texto);
      setErrorPrevio(problema);
      if (problema) return;
      mutate(texto, { onSuccess: () => alTerminar?.() });
    },
    [isPending, mutate],
  );

  return {
    justificar,
    guardando: isPending,
    guardada: mutacion.isSuccess,
    errorTexto: errorPrevio,
    error: mutacion.error ?? null,
    limpiar: useCallback(() => {
      reset();
      setErrorPrevio(null);
    }, [reset]),
  };
}
