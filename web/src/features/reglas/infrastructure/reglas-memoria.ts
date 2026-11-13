import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, type SesionMemoria } from "@/shared/infrastructure/memoria";
import { problemaDeValor, valorParaEnviar, type CatalogoReglas, type ReglasRepository } from "../domain/reglas";

/**
 * Reglas en memoria para pruebas y para el modo demostración. Sin catálogo se comporta como la API
 * con alguien que no es de administración: «prohibido». Valida igual que el servidor.
 */
export function crearReglasMemoria(opciones: {
  catalogo?: CatalogoReglas | null;
  sesion?: SesionMemoria;
  latenciaMs?: number;
  hoy?: () => string;
}): ReglasRepository {
  const { sesion, latenciaMs = 0, hoy = () => new Date().toISOString().slice(0, 10) } = opciones;
  let catalogo = opciones.catalogo ?? null;
  return {
    async catalogoReglas(signal) {
      await esperar(latenciaMs, signal);
      exigirSesion(sesion);
      if (!catalogo) throw new ErrorDeAplicacion("prohibido");
      return catalogo;
    },
    async editarRegla(id, valor) {
      await esperar(latenciaMs);
      exigirSesion(sesion);
      if (!catalogo) throw new ErrorDeAplicacion("prohibido");
      const regla = catalogo.grupos.flatMap((g) => g.reglas).find((r) => r.id === id);
      if (!regla) throw new ErrorDeAplicacion("no_encontrado");
      const problema = problemaDeValor(regla, valor);
      if (problema) throw new ErrorDeAplicacion("validacion", { campos: { valor: problema } });
      const nueva = { ...regla, valor: valorParaEnviar(regla, valor), verificado: hoy() };
      catalogo = {
        ...catalogo,
        grupos: catalogo.grupos.map((g) => ({ ...g, reglas: g.reglas.map((r) => (r.id === id ? nueva : r)) })),
      };
      return nueva;
    },
  };
}
