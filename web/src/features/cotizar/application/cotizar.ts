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
  AnalisisVuelo,
  Evidencia,
  DestinoFuente,
  OpcionesBuscador,
  ObjetivoFuente,
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

/** El enlace a la página oficial lleva un token que vence en 5 minutos: la cotización se vuelve a pedir antes. */
export const REFRESCO_COTIZACION_MS = 4 * 60_000;

export function useCotizacion(id: number) {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const consulta = useQuery({
    queryKey: claveDePersona(personaId, "cotizar", "detalle", id),
    queryFn: ({ signal }) => repositorio.obtener(id, signal),
    refetchInterval: REFRESCO_COTIZACION_MS,
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
    (destino: DestinoFuente, objetivo?: ObjetivoFuente) => {
      repositorio.registrarFuente(id, destino, objetivo).catch(() => {});
    },
    [repositorio, id],
  );
}

/**
 * Caso de uso «leer la página del vuelo»: se pide al abrir el desglose. Lo leído no cambia la comparación; un error de
 * red se muestra como lectura fallida, no interrumpe el desglose.
 */
export const SEGUIMIENTO_MS = 3000;
export const SEGUIMIENTO_INTENTOS = 15;

export function useAnalisisVuelo(id: number, vueloId: number) {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const pedido = useMutation<AnalisisVuelo, ErrorDeAplicacion, void>({
    mutationFn: async () => {
      try {
        return await repositorio.analizarVuelo(id, vueloId);
      } catch (error) {
        throw comoErrorDeAplicacion(error);
      }
    },
  });
  // Si otra persona (u otra pestaña) ya la está leyendo, la respuesta llega «pendiente»: se sigue cada 3 s, 15 veces.
  // Igual si el pedido agotó su plazo (58 s) o CloudFront cortó con un 504: la lectura puede seguir en la API.
  const queryClient = useQueryClient();
  const sinRespuesta = pedido.error?.tipo === "tiempo_agotado";
  const enCurso = pedido.data?.estado === "pendiente" || sinRespuesta;
  // una consulta nueva por cada pedido: el conteo de intentos empieza de cero
  const clave = claveDePersona(personaId, "cotizar", "analisis", id, vueloId, pedido.submittedAt);
  const seguimiento = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => repositorio.verAnalisis(id, vueloId, signal),
    enabled: enCurso,
    retry: false,
    refetchInterval: (q) =>
      (q.state.data?.estado ?? "pendiente") === "pendiente" && q.state.dataUpdateCount < SEGUIMIENTO_INTENTOS
        ? SEGUIMIENTO_MS
        : false,
  });
  const { mutate, isPending } = pedido;
  // Tras el plazo, el error que cuenta es el de la consulta (por ejemplo, una lectura que nunca quedó registrada)
  const error = sinRespuesta ? (seguimiento.error as ErrorDeAplicacion | null) : pedido.error;
  // Mientras llega la primera consulta tras el plazo, la lectura sigue «en curso» para la pantalla
  const esperandoEstado = sinRespuesta && !seguimiento.data && !seguimiento.error;
  const pedir = useCallback(() => mutate(), [mutate]);
  const consultas = queryClient.getQueryState(clave)?.dataUpdateCount ?? 0;
  // se lee siempre: React Query solo vuelve a pintar por los campos que se leyeron
  const buscando = seguimiento.isFetching;
  const data = enCurso && seguimiento.data ? seguimiento.data : pedido.data;
  return {
    isPending: isPending || esperandoEstado,
    error,
    data,
    mutate: pedir,
    /** Se consultó 15 veces y la lectura sigue en curso. */
    agotado: enCurso && data?.estado === "pendiente" && consultas >= SEGUIMIENTO_INTENTOS && !buscando,
  };
}


/**
 * Caso de uso «ver la evidencia guardada» (pieza 5): la guarda el trabajador después de decidir. Mientras está
 * `guardando`, se vuelve a consultar cada 15 s, hasta 20 veces (unos cinco minutos).
 */
export const EVIDENCIA_MS = 15_000;
export const EVIDENCIA_INTENTOS = 20;

export function useEvidencia(id: number, activo: boolean) {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  return useQuery<Evidencia, ErrorDeAplicacion>({
    queryKey: claveDePersona(personaId, "cotizar", "evidencia", id),
    queryFn: ({ signal }) => repositorio.evidencia(id, signal),
    enabled: activo,
    retry: false,
    refetchInterval: (q) =>
      q.state.data?.estado === "guardando" && q.state.dataUpdateCount < EVIDENCIA_INTENTOS ? EVIDENCIA_MS : false,
  });
}


export const OPCIONES_REINTENTO_MS = 2000;
/** Lo que se espera la consulta en vivo que dispara el clic: tarda de 18 a 30 s. */
export const OPCIONES_ESPERA_MS = 40_000;
/**
 * Lo consultado hasta una hora antes del clic vale como lo de este clic: el mismo pedido dentro de la hora el buscador lo
 * sirve de su caché y el servidor no guarda otra copia, así que nada más nuevo va a llegar. Cubre de sobra la diferencia
 * de relojes entre el navegador y el servidor.
 */
export const OPCIONES_VIGENCIA_MS = 60 * 60_000;

/** Una lectura de la capa: las opciones y, calculado al recibirlas, si ya son de este clic o si se acabó la espera. */
interface LecturaOpciones {
  readonly opciones: OpcionesBuscador;
  readonly vigentes: boolean;
  readonly agotado: boolean;
}

function esperaMas(l: LecturaOpciones | undefined): boolean {
  return l !== undefined && l.opciones.en_vivo === true && !l.vigentes && !l.agotado;
}

/**
 * Primera capa del desglose: lo que trajo el buscador. El mismo clic que abre el desglose abre la página oficial, que
 * consulta el buscador en vivo; lo nuevo llega a esta misma consulta. `clic` es el momento de ese clic (null: cerrado).
 * Con el buscador encendido (`en_vivo`) se reintenta cada 2 s, hasta 40 s, mientras no haya tarifas consultadas después
 * del clic (o en la hora anterior); mientras tanto se ve lo guardado, marcado. Con el buscador apagado, un solo pedido.
 */
export function useOpcionesBuscador(id: number, vueloId: number, clic: number | null) {
  const repositorio = useCotizarRepository();
  const personaId = usePersonaId();
  const consulta = useQuery<LecturaOpciones, ErrorDeAplicacion>({
    // cada apertura del desglose tiene su propia espera
    queryKey: claveDePersona(personaId, "cotizar", "opciones", id, vueloId, clic),
    queryFn: async ({ signal }) => {
      const opciones = await repositorio.opcionesBuscador(id, vueloId, signal);
      const desde = clic ?? Date.now();
      const vigentes = opciones.estado === "listo" && opciones.tarifas.length > 0 && opciones.consultado !== null
        && Date.parse(opciones.consultado) >= desde - OPCIONES_VIGENCIA_MS;
      return { opciones, vigentes, agotado: !vigentes && Date.now() - desde >= OPCIONES_ESPERA_MS };
    },
    enabled: clic !== null,
    retry: false,
    refetchInterval: (q) => (esperaMas(q.state.data) ? OPCIONES_REINTENTO_MS : false),
  });
  const lectura = consulta.data;
  return {
    data: lectura?.opciones ?? null,
    error: consulta.error,
    /** Todavía puede llegar algo: la primera consulta, o la espera de lo que trae el clic. */
    esperando: clic !== null && (consulta.isPending || esperaMas(lectura)),
    /** Las tarifas que se ven son de este clic (o de la hora anterior): sin marca. */
    vigentes: lectura?.vigentes ?? false,
    /** Se esperó la consulta en vivo y no llegó nada nuevo. */
    agotado: Boolean(lectura?.opciones.en_vivo && lectura.agotado),
  };
}
