"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { nuevaClaveIdempotencia } from "@/shared/application/clave-idempotencia";
import { crearContextoRepositorio } from "@/shared/application/contexto-repositorio";
import { claveDePersona, usePersonaId } from "@/shared/application/identidad";
import { comoErrorDeAplicacion, type ErrorDeAplicacion } from "@/shared/domain/errores";
import type {
  Cotizacion,
  CotizarRepository,
  DecisionPedida,
  DestinoFuente,
  PedidoCotizacion,
} from "../domain/cotizar";

const contexto = crearContextoRepositorio<CotizarRepository>("CotizarRepository");
export const CotizarRepositoryProvider = contexto.Proveedor;
export const useCotizarRepository = contexto.useRepositorio;

/** Los datos propios se piden con cada letra (responden al instante); Google, solo tras una pausa al escribir. */
export const ESPERA_GOOGLE_MS = 400;
const LETRAS_LOCAL = 2;
const LETRAS_GOOGLE = 3;

function useRetrasado(valor: string, ms: number): string {
  const [retrasado, setRetrasado] = useState(valor);
  useEffect(() => {
    const t = setTimeout(() => setRetrasado(valor), ms);
    return () => clearTimeout(t);
  }, [valor, ms]);
  return retrasado;
}

export function useFormularioCotizacion() {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "cotizar", "formulario"),
    queryFn: ({ signal }) => repositorio.formulario(signal),
    staleTime: 5 * 60_000,
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

/**
 * Sugerencias del campo de lugar mientras se escribe. Primero los datos propios; con 3 letras o más y tras una
 * pausa, también Google (el servidor aplica los topes). Una respuesta de un texto viejo nunca pisa la del actual.
 * Solo se consulta si `escribiendo`: un valor puesto por código (caso de ejemplo, borrador recuperado, lugar ya
 * elegido) no gasta cupo de Google ni cuenta para los topes.
 */
export function useSugerenciasLugar(texto: string, escribiendo: boolean) {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const actual = texto.trim();
  const local = actual;
  const google = useRetrasado(actual, ESPERA_GOOGLE_MS);
  const consultaLocal = useQuery({
    queryKey: claveDePersona(personaId, "cotizar", "lugares", local, false),
    queryFn: ({ signal }) => repositorio.buscarLugares(local, false, signal),
    enabled: escribiendo && local.length >= LETRAS_LOCAL,
    staleTime: 10 * 60_000,
    placeholderData: keepPreviousData,
  });
  const consultaGoogle = useQuery({
    queryKey: claveDePersona(personaId, "cotizar", "lugares", google, true),
    queryFn: ({ signal }) => repositorio.buscarLugares(google, true, signal),
    enabled: escribiendo && google.length >= LETRAS_GOOGLE && google === actual,
    staleTime: 10 * 60_000,
    retry: false,
  });
  // Mientras llega la respuesta del texto nuevo se siguen viendo las sugerencias anteriores (sin parpadeo),
  // pero no cuentan como respuesta: Enter espera la del texto actual.
  const deGoogle = consultaGoogle.data && google === actual ? consultaGoogle.data : null;
  const propios = consultaLocal.data && !consultaLocal.isPlaceholderData ? consultaLocal.data : null;
  const datos = deGoogle ?? propios;
  const mostrados = datos ?? consultaLocal.data ?? null;
  return {
    resultados: actual.length >= LETRAS_LOCAL ? (mostrados?.resultados ?? []) : [],
    avisoGoogle: datos?.aviso_google ?? null,
    carretera: mostrados?.carretera ?? { factor: 1.3, velocidad_kmh: 70 },
    /** Aún no hay respuesta para el texto actual. */
    esperando: escribiendo && actual.length >= LETRAS_LOCAL && !datos,
    /** Hay respuesta para el texto actual (aunque esté vacía). */
    listo: Boolean(datos),
    error: (consultaLocal.error as ErrorDeAplicacion | null) ?? null,
  };
}

/** Para Enter antes de que lleguen las sugerencias: las pide ya (o reusa la petición en curso). */
export function useBuscarLugarAhora() {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  return useCallback(
    (texto: string) =>
      queryClient.fetchQuery({
        queryKey: claveDePersona(personaId, "cotizar", "lugares", texto.trim(), false),
        queryFn: ({ signal }) => repositorio.buscarLugares(texto.trim(), false, signal),
        staleTime: 10 * 60_000,
      }),
    [queryClient, personaId, repositorio],
  );
}

/**
 * Una clave de idempotencia por envío: reintentar lo mismo (tras un corte o un error) reutiliza la clave,
 * así el servidor no repite la búsqueda ni la decisión; un envío distinto, o uno después de un éxito, usa otra.
 */
function useClavePorEnvio() {
  const ultima = useRef<{ firma: string; clave: string } | null>(null);
  return {
    para(envio: unknown): string {
      const firma = JSON.stringify(envio);
      if (ultima.current?.firma !== firma) ultima.current = { firma, clave: nuevaClaveIdempotencia() };
      return ultima.current.clave;
    },
    olvidar() {
      ultima.current = null;
    },
  };
}

/** Caso de uso «cotizar»: busca y deja la comparación en caché para abrirla sin otra petición. */
export function useCotizar() {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  const clave = useClavePorEnvio();
  return useMutation<Cotizacion, ErrorDeAplicacion, PedidoCotizacion>({
    mutationFn: async (pedido) => {
      try {
        return await repositorio.cotizar(pedido, clave.para(pedido));
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: (c) => {
      clave.olvidar();
      queryClient.setQueryData(claveDePersona(personaId, "cotizar", "detalle", c.id), c);
    },
  });
}

export function useCotizacion(id: number) {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "cotizar", "detalle", id),
    queryFn: ({ signal }) => repositorio.obtener(id, signal),
  });
  return { ...consulta, error: consulta.error as ErrorDeAplicacion | null };
}

/** Caso de uso «decidir»: guarda la decisión, crea el viaje y refresca los viajes de la persona. */
export function useDecidir(id: number) {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const queryClient = useQueryClient();
  const clave = useClavePorEnvio();
  const mutacion = useMutation<Cotizacion, ErrorDeAplicacion, DecisionPedida>({
    mutationFn: async (decision) => {
      try {
        return await repositorio.decidir(id, decision, clave.para({ id, decision }));
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
    onSuccess: (c) => {
      clave.olvidar();
      queryClient.setQueryData(claveDePersona(personaId, "cotizar", "detalle", id), c);
      void queryClient.invalidateQueries({ queryKey: claveDePersona(personaId, "viajes") });
    },
  });
  const { mutate, isPending } = mutacion;
  const decidir = useCallback(
    (decision: DecisionPedida, alTerminar?: (c: Cotizacion) => void) => {
      if (isPending) return;
      mutate(decision, { onSuccess: (c) => alTerminar?.(c) });
    },
    [isPending, mutate],
  );
  return { ...mutacion, decidir };
}

/**
 * Caso de uso «ver la fuente»: el enlace abre Google en otra pestaña por sí solo; esto solo deja el rastro del clic.
 * Si el registro falla no se interrumpe a la persona: la verificación importa más que el rastro.
 */
export function useRegistrarFuente(id: number) {
  const repositorio = useCotizarRepository();
  return useCallback(
    (destino: DestinoFuente, hotelId?: number) => {
      repositorio.registrarFuente(id, destino, hotelId).catch(() => {});
    },
    [repositorio, id],
  );
}
