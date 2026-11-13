import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import {
  accionesPosibles,
  bloqueoSeComprara,
  requiereMotivo,
  validarRegistro,
  type CompraDetalle,
  type ComprasRepository,
  type EstadoCompra,
} from "../domain/compras";

const TEXTO: Readonly<Record<EstadoCompra, string>> = {
  solicitada: "Solicitud de compra enviada",
  en_analisis: "En análisis",
  se_comprara: "Se va a comprar",
  no_se_comprara: "No se va a comprar",
  comprada: "Comprada",
  cancelada: "Cancelada",
};

/** Compras en memoria, con las reglas del contrato: versión esperada, transiciones y viaje aprobado. */
export function crearComprasMemoria(opciones: {
  compras?: readonly CompraDetalle[];
  /** Ids de compras del propio viaje de quien mira: cambiarlas responde «autoaprobación». */
  propias?: readonly number[];
  sesion?: SesionMemoria;
  latenciaMs?: number;
}): ComprasRepository {
  const { sesion, latenciaMs = 0, propias = [] } = opciones;
  const compras = new Map<number, CompraDetalle>((opciones.compras ?? []).map((c) => [c.id, c]));

  function una(id: number): CompraDetalle {
    const c = compras.get(id);
    if (!c) throw new ErrorDeAplicacion("no_encontrado");
    return c;
  }

  function guardar(c: CompraDetalle, cambios: Partial<CompraDetalle>): CompraDetalle {
    const nueva = { ...c, ...cambios, version: c.version + 1 } as CompraDetalle;
    compras.set(c.id, nueva);
    return nueva;
  }

  function comprobar(id: number, version: number): CompraDetalle {
    const c = una(id);
    if (propias.includes(id)) {
      throw new ErrorDeAplicacion("autoaprobacion", { mensaje: "Nadie decide la compra de su propio viaje: debe hacerlo otra persona de administración." });
    }
    if (c.version !== version) throw new ErrorDeAplicacion("cambio_ajeno");
    return c;
  }

  return {
    async lista(signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      return [...compras.values()];
    },
    async detalle(id, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      return una(id);
    },
    async cambiarEstado(id, accion, version, motivo) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      const c = comprobar(id, version);
      if (!accionesPosibles(c).includes(accion)) throw new ErrorDeAplicacion("estado_invalido");
      if (accion === "se_comprara" && bloqueoSeComprara(c)) {
        throw new ErrorDeAplicacion("estado_invalido", { mensaje: bloqueoSeComprara(c)! });
      }
      if (requiereMotivo(accion) && motivo.trim().length < 5) {
        throw new ErrorDeAplicacion("validacion", { campos: { motivo: "Escribe el motivo (5 caracteres o más)." } });
      }
      return guardar(c, { estado: accion, estado_texto: TEXTO[accion], motivo: motivo.trim() || c.motivo });
    },
    async registrar(id, version, registro) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      const c = comprobar(id, version);
      if (c.estado !== "se_comprara") throw new ErrorDeAplicacion("estado_invalido");
      const errores = validarRegistro(registro);
      if (Object.keys(errores).length) throw new ErrorDeAplicacion("validacion", { campos: errores as Record<string, string> });
      const pagado = Number(registro.precio_pagado).toFixed(2);
      const cotizado = Number(c.precio_cotizado_usd ?? 0);
      return guardar(c, {
        estado: "comprada", estado_texto: TEXTO.comprada, localizador: registro.localizador.toUpperCase(),
        vendedor: registro.vendedor.trim(), precio_pagado_usd: pagado, comprada: new Date().toISOString().slice(0, 19) + "Z",
        frente_presupuesto: {
          presupuesto_usd: c.viaje.presupuesto_usd, cotizado_usd: c.precio_cotizado_usd,
          diferencia_usd: (Number(pagado) - cotizado).toFixed(2),
        },
      });
    },
    async analizar(id) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      una(id);
      return { estado: "no_disponible", motivo: "En la demostración no se lee la página del vuelo.", leido: null, captura_url: null, aviso_precio: null };
    },
  };
}
