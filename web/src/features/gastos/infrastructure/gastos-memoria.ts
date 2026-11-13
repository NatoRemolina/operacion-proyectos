import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, paginar, type SesionMemoria } from "@/shared/infrastructure/memoria";
import {
  JUSTIFICACION_MINIMO,
  limpiarJustificacion,
  validarArchivo,
  type GastoDetalle,
  type GastosRepository,
  type Justificacion,
} from "../domain/gastos";

export interface ViajePropioMemoria {
  readonly id: number;
  readonly codigo: string;
  readonly enCurso: boolean;
}

/**
 * Gastos en memoria para pruebas y para el modo demostración. No lee el recibo: aplica una
 * regla fija y visible para que el recorrido muestre los dos resultados posibles.
 *  - Sin viaje propio (elegido o en curso) queda en revisión.
 *  - Un PDF queda en revisión (simula una lectura con poca confianza).
 *  - Una imagen con viaje queda aprobada automáticamente.
 * Respeta la idempotencia del contrato: misma clave y mismo archivo devuelven el mismo gasto;
 * misma clave y otro archivo, conflicto.
 */
export function crearGastosMemoria(opciones: {
  gastos?: readonly GastoDetalle[];
  viajesPropios?: readonly ViajePropioMemoria[];
  sesion?: SesionMemoria;
  latenciaMs?: number;
  hoy?: () => string;
}): GastosRepository {
  const { viajesPropios = [], sesion, latenciaMs = 0 } = opciones;
  const hoy = opciones.hoy ?? (() => new Date().toISOString().slice(0, 10));
  const gastos: GastoDetalle[] = [...(opciones.gastos ?? [])];
  const porClave = new Map<string, { firma: string; gasto: GastoDetalle }>();
  const archivos = new Map<number, File>();
  const urls = new Map<number, string>();
  let siguienteId = Math.max(1000, ...gastos.map((g) => g.id)) + 1;
  let siguienteJustificacion = 1;
  const nuevaJustificacion = (texto: string): Justificacion => ({
    id: siguienteJustificacion++,
    tipo: "texto",
    canal: "web",
    texto,
    transcripcion: "no_aplica",
    creado: new Date().toISOString(),
  });

  const firmaDe = (archivo: File) => `${archivo.name}|${archivo.size}|${archivo.lastModified}`;

  return {
    async listar(filtro, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const visibles = gastos
        .filter((g) => filtro.viajeId === undefined || g.viaje?.id === filtro.viajeId)
        .filter((g) => !filtro.estado || g.estado === filtro.estado)
        .toSorted((a, b) => b.creado.localeCompare(a.creado));
      return paginar(visibles, filtro.limite, filtro.cursor);
    },

    async obtener(id, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const gasto = gastos.find((g) => g.id === id);
      if (!gasto) throw new ErrorDeAplicacion("no_encontrado");
      return gasto;
    },

    async enviar({ archivo, viajeId, claveIdempotencia, justificacion }, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const invalido = validarArchivo(archivo);
      if (invalido) throw new ErrorDeAplicacion(invalido);

      const previo = porClave.get(claveIdempotencia);
      if (previo) {
        if (previo.firma !== firmaDe(archivo)) throw new ErrorDeAplicacion("conflicto");
        return previo.gasto;
      }

      const viaje =
        viajeId === null
          ? viajesPropios.find((v) => v.enCurso)
          : viajesPropios.find((v) => v.id === viajeId);
      const esPdf = archivo.type === "application/pdf";
      const motivos: string[] = [];
      const alertas: string[] = [];
      if (!viaje) {
        motivos.push("sin_viaje");
        alertas.push("No encontramos un viaje tuyo para este recibo; administración lo asignará.");
      }
      if (esPdf) {
        motivos.push("lectura_dudosa");
        alertas.push("El total no se pudo leer con suficiente seguridad.");
      }
      const enRevision = motivos.length > 0;
      const id = siguienteId++;
      const gasto: GastoDetalle = {
        id,
        viaje: viaje ? { id: viaje.id, codigo: viaje.codigo } : null,
        comercio: enRevision ? null : "Comercio de demostración",
        fecha: hoy(),
        categoria: enRevision ? null : "Alimentación",
        total: esPdf ? null : "42.50",
        moneda: esPdf ? null : "USD",
        total_usd: esPdf ? null : "42.50",
        estado: enRevision ? "revision" : "aprobado_auto",
        estado_texto: enRevision ? "En revisión" : "Aprobado",
        creado: new Date().toISOString(),
        subtotal: esPdf ? null : "38.64",
        impuesto: esPdf ? null : "3.86",
        propina: null,
        motivos,
        alertas,
        canal: "web",
        documento_id: id,
        lectura: { origen: "demostracion", confianza: esPdf ? 0.41 : 0.97 },
        justificaciones:
          limpiarJustificacion(justificacion ?? "").length >= JUSTIFICACION_MINIMO
            ? [nuevaJustificacion(limpiarJustificacion(justificacion ?? ""))]
            : [],
      };
      gastos.unshift(gasto);
      archivos.set(id, archivo);
      porClave.set(claveIdempotencia, { firma: firmaDe(archivo), gasto });
      return gasto;
    },

    async justificar(id, texto, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const indice = gastos.findIndex((g) => g.id === id);
      if (indice < 0) throw new ErrorDeAplicacion("no_encontrado");
      const limpio = limpiarJustificacion(texto);
      if (limpio.length < JUSTIFICACION_MINIMO) {
        throw new ErrorDeAplicacion("validacion", {
          campos: { texto: "Escribe para qué fue el gasto, aunque sea en pocas palabras." },
        });
      }
      const actual = gastos[indice]!;
      const nuevo = { ...actual, justificaciones: [...actual.justificaciones, nuevaJustificacion(limpio)] };
      gastos[indice] = nuevo;
      return nuevo;
    },

    urlOriginal(documentoId) {
      const archivo = archivos.get(documentoId);
      if (!archivo || typeof URL.createObjectURL !== "function") return null;
      let url = urls.get(documentoId);
      if (!url) {
        url = URL.createObjectURL(archivo);
        urls.set(documentoId, url);
      }
      return url;
    },

    // El libro lo arma el servidor (cuentas contables, alcance por permiso): en memoria no se imita.
    urlLibroContable() {
      return null;
    },
  };
}
