import type { Permiso } from "@/shared/domain/navegacion";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, paginar, type SesionMemoria } from "@/shared/infrastructure/memoria";
import {
  problemasDeProyecto,
  type DatosProyecto,
  type ProyectoResumen,
  type ProyectosRepository,
  type TableroProyecto,
} from "../domain/proyectos";

/**
 * Proyectos en memoria para pruebas y para el modo demostración. Imita los permisos de la API:
 * colaboración no ve la lista, solo administración crea y edita, y un proyecto sin tablero no existe.
 * Sin plataforma conectada no hay descargas (`null`).
 */
export function crearProyectosMemoria(
  opciones: {
    proyectos?: ProyectoResumen[];
    tableros?: TableroProyecto[];
    permiso?: Permiso;
    sesion?: SesionMemoria;
    latenciaMs?: number;
  } = {},
): ProyectosRepository {
  const { sesion, latenciaMs = 0, permiso = "colaborador" } = opciones;
  const proyectos = [...(opciones.proyectos ?? [])];
  const tableros = new Map((opciones.tableros ?? []).map((t) => [t.proyecto.id, t]));

  function soloAdmin() {
    if (permiso !== "admin") throw new ErrorDeAplicacion("prohibido");
  }

  function validar(datos: DatosProyecto): DatosProyecto {
    const problemas = problemasDeProyecto(datos);
    if (Object.keys(problemas).length) throw new ErrorDeAplicacion("validacion", { campos: problemas as Record<string, string> });
    return { ...datos, nombre: datos.nombre.trim(), moneda: datos.moneda.trim().toUpperCase() };
  }

  function conDatos(base: ProyectoResumen, datos: DatosProyecto): ProyectoResumen {
    return { ...base, ...datos, cliente: datos.cliente.trim() || null, ciudad: datos.ciudad.trim() || null };
  }

  return {
    async listar({ limite, cursor }, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (permiso === "colaborador") throw new ErrorDeAplicacion("prohibido");
      return paginar([...proyectos].sort((a, b) => b.id - a.id), limite, cursor);
    },
    async obtener(id, signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      const tablero = tableros.get(id);
      if (!tablero || permiso === "colaborador") throw new ErrorDeAplicacion("no_encontrado");
      return tablero;
    },
    async crear(datos) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      soloAdmin();
      const limpios = validar(datos);
      const nuevo = conDatos(
        {
          id: Math.max(0, ...proyectos.map((p) => p.id)) + 1,
          viajes: 0,
          gastos: 0,
          previsto_usd: "0.00",
          real_usd: "0.00",
          diferencia_usd: "0.00",
          ...limpios,
          cliente: null,
          ciudad: null,
        },
        limpios,
      );
      proyectos.push(nuevo);
      return nuevo;
    },
    async editar(id, datos) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      soloAdmin();
      const indice = proyectos.findIndex((p) => p.id === id);
      if (indice < 0) throw new ErrorDeAplicacion("no_encontrado");
      const editado = conDatos(proyectos[indice]!, validar(datos));
      proyectos[indice] = editado;
      const tablero = tableros.get(id);
      if (tablero) tableros.set(id, { ...tablero, proyecto: editado });
      return editado;
    },
    urlCsv: () => null,
    urlLibroContable: () => null,
  };
}
