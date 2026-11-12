import type { ViajeResumen } from "@/features/viajes/domain/viajes";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import {
  problemaDeMotivo,
  type AccionViaje,
  type AdministracionRepository,
  type ResumenAdmin,
} from "../domain/administracion";

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
  sesion?: SesionMemoria;
  latenciaMs?: number;
}): AdministracionRepository {
  const { sesion, latenciaMs = 0 } = opciones;
  const viajes = opciones.viajes ?? [];
  return {
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
  };
}
