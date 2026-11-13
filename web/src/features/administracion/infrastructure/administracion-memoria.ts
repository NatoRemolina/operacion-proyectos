import { CATEGORIAS, type GastoDetalle } from "@/features/gastos/domain/gastos";
import type { ViajeResumen } from "@/features/viajes/domain/viajes";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import {
  problemaDeMotivo,
  type AccionViaje,
  type AdministracionRepository,
  type ResumenAdmin,
} from "../domain/administracion";
import type { BuzonSimulado } from "../domain/buzon";
import { problemaDeMotivoExcepcion, type DatosRevision } from "../domain/revision";
import type { CatalogoReglas } from "@/features/reglas/domain/reglas";
import { crearReglasMemoria } from "@/features/reglas/infrastructure/reglas-memoria";

/** Las mismas transiciones que `viajes.TRANSICIONES` del servidor. */
const TRANSICIONES: Record<AccionViaje, { desde: ViajeResumen["estado"][]; hacia: ViajeResumen["estado"]; texto: string; paso: string }> = {
  aprobar: { desde: ["pendiente_aprobacion"], hacia: "aprobado", texto: "Aprobado", paso: "presupuesto aprobado" },
  rechazar: { desde: ["pendiente_aprobacion"], hacia: "rechazado", texto: "Rechazado", paso: "presupuesto rechazado" },
  reabrir: { desde: ["aprobado", "rechazado", "cerrado"], hacia: "pendiente_aprobacion", texto: "Pendiente de aprobación", paso: "viaje reabierto" },
  cerrar: { desde: ["aprobado"], hacia: "cerrado", texto: "Cerrado", paso: "viaje cerrado" },
};

/**
 * Administración en memoria para pruebas y para el modo demostración. Sin resumen (`null` o sin
 * datos) se comporta como la API con alguien que no es de administración: «prohibido».
 * `viajes` es la misma lista que usa el adaptador de viajes en memoria: los cambios de estado se ven allí.
 */
export function crearAdministracionMemoria(opciones: {
  resumen?: ResumenAdmin | null;
  viajes?: ViajeResumen[];
  gastos?: GastoDetalle[];
  /** Lo que la revisión necesita además de la ficha; sin él se arma con la ficha y los viajes. */
  datosRevision?: Record<number, DatosRevision>;
  /** Sin buzón, responde «prohibido», como la API a quien no es de administración. */
  buzon?: BuzonSimulado | null;
  /** Sin catálogo, las reglas responden «prohibido», como la API a quien no es de administración. */
  reglas?: CatalogoReglas | null;
  sesion?: SesionMemoria;
  latenciaMs?: number;
}): AdministracionRepository {
  const { sesion, latenciaMs = 0 } = opciones;
  const viajes = opciones.viajes ?? [];
  const gastos = opciones.gastos ?? [];
  return {
    ...crearReglasMemoria({ catalogo: opciones.reglas ?? null, sesion, latenciaMs }),
    async resumen(signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.resumen) throw new ErrorDeAplicacion("prohibido");
      return opciones.resumen;
    },

    async cambiarEstadoViaje(id, { accion, motivo = "", confirmarPrecio = false }) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      if (!opciones.resumen) throw new ErrorDeAplicacion("prohibido");
      const indice = viajes.findIndex((v) => v.id === id);
      if (indice < 0) throw new ErrorDeAplicacion("no_encontrado");
      const viaje = viajes[indice]!;
      const regla = TRANSICIONES[accion];
      if ((accion === "aprobar" || accion === "rechazar") && viaje.propio) throw new ErrorDeAplicacion("autoaprobacion");
      if (!regla.desde.includes(viaje.estado)) throw new ErrorDeAplicacion("estado_invalido");
      const problema = accion === "rechazar" ? problemaDeMotivo(motivo) : null;
      if (problema) throw new ErrorDeAplicacion("validacion", { campos: { motivo: problema } });
      if (accion === "aprobar" && viaje.precio_por_confirmar && !confirmarPrecio) {
        throw new ErrorDeAplicacion("precio_por_confirmar", { campos: { precio: viaje.precio_por_confirmar } });
      }
      const nuevo: ViajeResumen = { ...viaje, estado: regla.hacia, estado_texto: regla.texto, precio_por_confirmar: null };
      viajes[indice] = nuevo;
      return {
        viaje: {
          ...nuevo,
          presupuesto_detalle: [],
          motivo: motivo.trim() || null,
          aprobado_en: regla.hacia === "aprobado" ? new Date().toISOString() : null,
        },
        mensaje: `${viaje.codigo}: ${regla.paso}.`,
      };
    },

    async revisarGasto(id, { version, accion, motivo = "", campos = {}, viajeId }) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      if (!opciones.resumen) throw new ErrorDeAplicacion("prohibido");
      const indice = gastos.findIndex((g) => g.id === id);
      if (indice < 0) throw new ErrorDeAplicacion("no_encontrado");
      const gasto = gastos[indice]!;
      if (gasto.propio) throw new ErrorDeAplicacion("prohibido");
      if ((gasto.version ?? 0) !== version) throw new ErrorDeAplicacion("cambio_ajeno");
      const problema =
        accion === "rechazar" ? problemaDeMotivo(motivo) : accion === "excepcion" ? problemaDeMotivoExcepcion(motivo) : null;
      if (problema) throw new ErrorDeAplicacion("validacion", { mensaje: problema, campos: { motivo: problema } });
      const viaje = viajeId === undefined ? gasto.viaje : viajes.find((v) => v.id === viajeId) ?? null;
      if (viajeId && !viaje) throw new ErrorDeAplicacion("validacion", { mensaje: "Ese viaje no existe." });
      // El método de pago y el canal no salen en la ficha: se guardan en los datos de revisión.
      const visibles = Object.fromEntries(
        Object.entries(campos).filter(([campo]) => campo !== "metodo_pago" && campo !== "canal_reserva"),
      );
      const corregido: GastoDetalle =
        accion === "rechazar" ? gasto : { ...gasto, ...visibles, viaje: viaje ? { id: viaje.id, codigo: viaje.codigo } : null };
      // Como el servidor: aprobar vuelve a pasar las reglas y, si hay motivos, el gasto sigue en revisión.
      const aprobado = accion === "excepcion" || (accion === "aprobar" && gasto.motivos.length === 0);
      const estado = accion === "rechazar" ? "rechazado" : aprobado ? "aprobado" : "revision";
      const nuevo: GastoDetalle = {
        ...corregido,
        estado,
        estado_texto: { rechazado: "Rechazado", aprobado: "Aprobado", revision: "En revisión" }[estado],
        motivo_rechazo: accion === "rechazar" ? motivo.trim() : (gasto.motivo_rechazo ?? null),
        version: version + 1,
      };
      gastos[indice] = nuevo;
      if (opciones.datosRevision?.[id]) {
        const previos = opciones.datosRevision[id];
        opciones.datosRevision[id] = {
          ...previos,
          version: version + 1,
          metodo_pago: campos.metodo_pago === undefined ? previos.metodo_pago : campos.metodo_pago,
          canal_reserva: campos.canal_reserva === undefined ? previos.canal_reserva : campos.canal_reserva,
        };
      }
      return nuevo;
    },

    async datosRevision(id, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.resumen) throw new ErrorDeAplicacion("prohibido");
      const gasto = gastos.find((g) => g.id === id);
      if (!gasto) throw new ErrorDeAplicacion("no_encontrado");
      return (
        opciones.datosRevision?.[id] ?? {
          gasto_id: id,
          version: gasto.version ?? 0,
          metodo_pago: null,
          canal_reserva: null,
          lectura_original: null,
          soporte: gasto.documento_id === null ? null : { documento_id: gasto.documento_id, nombre: null, forma: "imagen" },
          categorias: Object.entries(CATEGORIAS).map(([clave, nombre]) => ({ clave, nombre })),
          viajes: viajes
            .filter((v) => v.estado !== "rechazado")
            .map((v) => ({
              id: v.id,
              codigo: v.codigo,
              estado: v.estado,
              estado_texto: v.estado_texto,
              titular: v.titular?.nombre ?? null,
              origen: v.origen,
              destino: v.destino,
              ida: v.ida,
              regreso: v.regreso,
            })),
          propio: gasto.propio ?? false,
          aviso_propio: gasto.propio ? "Nadie revisa sus propios gastos: debe hacerlo otra persona de administración." : null,
        }
      );
    },

    urlAudioJustificacion() {
      return null;
    },

    async buzon(signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!opciones.buzon) throw new ErrorDeAplicacion("prohibido");
      return opciones.buzon;
    },

    async leerBuzon({ nombres, viajeId }) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      const buzon = opciones.buzon;
      if (!buzon) throw new ErrorDeAplicacion("prohibido");
      const viaje = viajeId === null ? null : buzon.viajes.find((v) => v.id === viajeId);
      if (viajeId !== null && !viaje) {
        throw new ErrorDeAplicacion("validacion", { campos: { viaje_id: "Ese viaje no existe." } });
      }
      const conocidos = new Set(buzon.mensajes.map((m) => m.nombre));
      // Como el servidor: cada correo leído es un gasto nuevo que espera revisión (la demostración no lee recibos).
      const leidos = nombres.filter((n) => conocidos.has(n)).map((n, i) => ({
        id: 9000 + gastos.length + i,
        viaje: viaje ? { id: viaje.id, codigo: viaje.codigo } : null,
        comercio: n,
        fecha: null,
        categoria: null,
        total: null,
        moneda: null,
        total_usd: null,
        estado: "revision" as const,
        estado_texto: "En revisión",
        creado: new Date().toISOString(),
        propio: false,
      }));
      return {
        leidos,
        errores: nombres.filter((n) => !conocidos.has(n)).map((nombre) => ({ nombre, mensaje: "No está en el buzón simulado." })),
      };
    },
  };
}
