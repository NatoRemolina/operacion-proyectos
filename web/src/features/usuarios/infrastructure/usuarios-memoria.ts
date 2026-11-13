import type { Permiso } from "@/shared/domain/navegacion";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { esperar, exigirSesion, paginar, type SesionMemoria } from "@/shared/infrastructure/memoria";
import {
  CLAVE_CORTA,
  PERMISOS,
  problemaDeCargo,
  problemasDeCuenta,
  type Cargo,
  type Referencia,
  type ResultadoUsuario,
  type Usuario,
  type UsuariosRepository,
} from "../domain/usuarios";

const NO_QUITAR_ROL = "No puedes quitarte tu propio rol ni dejar la plataforma sin administradores.";
const NO_DESACTIVAR = "No puedes desactivar tu propia cuenta ni al último administrador.";

/**
 * Cuentas en memoria para pruebas y para el modo demostración. Imita a la API: solo administración,
 * las mismas protecciones (`yo` es la cuenta de la sesión) y los mismos mensajes.
 */
export function crearUsuariosMemoria(
  opciones: {
    usuarios?: Usuario[];
    cargos?: Cargo[];
    proyectos?: Referencia[];
    permiso?: Permiso;
    yo?: number;
    sesion?: SesionMemoria;
    latenciaMs?: number;
  } = {},
): UsuariosRepository {
  const { sesion, latenciaMs = 0, permiso = "colaborador", yo = 0 } = opciones;
  const usuarios = [...(opciones.usuarios ?? [])];
  let cargos = [...(opciones.cargos ?? [])];
  const nombresProyectos = new Map((opciones.proyectos ?? []).map((p) => [p.id, p.nombre]));

  async function preparar(signal?: AbortSignal) {
    await esperar(latenciaMs, signal);
    exigirSesion(sesion);
    if (permiso !== "admin") throw new ErrorDeAplicacion("prohibido");
  }

  function cuenta(id: number): Usuario {
    const u = usuarios.find((x) => x.id === id);
    if (!u) throw new ErrorDeAplicacion("no_encontrado");
    return u;
  }

  function guardar(id: number, cambios: Partial<Usuario>, mensaje: string): ResultadoUsuario {
    const indice = usuarios.findIndex((x) => x.id === id);
    const usuario = { ...usuarios[indice]!, ...cambios };
    usuarios[indice] = usuario;
    cargos = cargos.map((c) => ({ ...c, personas: usuarios.filter((u) => u.cargo?.id === c.id).length }));
    return { usuario, mensaje };
  }

  function invalido(campo: string, mensaje: string): ErrorDeAplicacion {
    return new ErrorDeAplicacion("validacion", { campos: { [campo]: mensaje } });
  }

  function otrosAdminsActivos(excepto: number) {
    return usuarios.filter((u) => u.rol === "admin" && u.activo && u.id !== excepto).length;
  }

  function cargoActivo(cargoId: number | null): Referencia | null {
    if (!cargoId) return null;
    const c = cargos.find((x) => x.id === cargoId && x.activo);
    if (!c) throw invalido("cargo_id", "Ese cargo no existe o está desactivado.");
    return { id: c.id, nombre: c.nombre };
  }

  return {
    async listar({ limite, cursor }, signal) {
      await preparar(signal);
      return paginar([...usuarios].sort((a, b) => b.id - a.id), limite, cursor);
    },
    async crear(datos) {
      await preparar();
      const problemas = problemasDeCuenta(datos);
      if (Object.keys(problemas).length) throw new ErrorDeAplicacion("validacion", { campos: problemas as Record<string, string> });
      const correo = datos.correo.trim().toLowerCase();
      if (usuarios.some((u) => u.correo === correo)) throw invalido("correo", "Ya existe una cuenta con ese correo.");
      const id = Math.max(0, ...usuarios.map((u) => u.id)) + 1;
      usuarios.push({
        id,
        codigo: `P-${String(id).padStart(4, "0")}`,
        correo,
        nombre: datos.nombre.trim() || correo,
        rol: datos.rol,
        rol_texto: PERMISOS.find((p) => p.valor === datos.rol)!.texto,
        cargo: cargoActivo(datos.cargo_id),
        proyectos: [],
        activo: true,
        telegram: { vinculado: false, usuario: null },
        ultima_sesion: null,
        creado: new Date().toISOString(),
      });
      return guardar(id, {}, "Cuenta creada. Comparte la contraseña inicial por un canal seguro.");
    },
    async cambiarRol(id, rol) {
      await preparar();
      const u = cuenta(id);
      if (u.rol === "admin" && rol !== "admin" && (id === yo || !otrosAdminsActivos(id))) {
        throw new ErrorDeAplicacion("estado_invalido", { mensaje: NO_QUITAR_ROL });
      }
      const texto = PERMISOS.find((p) => p.valor === rol)!.texto;
      return guardar(id, { rol, rol_texto: texto, proyectos: rol === "gestor" ? u.proyectos : [] },
        `Permiso de ${u.nombre} cambiado; sus sesiones abiertas se cerraron.`);
    },
    async cambiarEstado(id, activo) {
      await preparar();
      const u = cuenta(id);
      if (u.activo === activo) {
        return guardar(id, {}, `Sin cambios: la cuenta de ${u.nombre} ya estaba ${activo ? "activa" : "desactivada"}.`);
      }
      if (!activo && (id === yo || (u.rol === "admin" && !otrosAdminsActivos(id)))) {
        throw new ErrorDeAplicacion("estado_invalido", { mensaje: NO_DESACTIVAR });
      }
      return guardar(id, { activo }, `Cuenta de ${u.nombre} ${activo ? "reactivada" : "desactivada"}; sus sesiones abiertas se cerraron.`);
    },
    async cambiarCargo(id, cargoId) {
      await preparar();
      const u = cuenta(id);
      return guardar(id, { cargo: cargoActivo(cargoId) }, `Cargo de ${u.nombre} actualizado.`);
    },
    async asignarProyectos(id, proyectosIds) {
      await preparar();
      const u = cuenta(id);
      const elegidos = [...new Set(proyectosIds)].sort((a, b) => a - b);
      return guardar(id, { proyectos: elegidos.map((p) => ({ id: p, nombre: nombresProyectos.get(p) ?? `Proyecto ${p}` })) },
        `Proyectos de ${u.nombre} guardados (${elegidos.length}).`);
    },
    async restablecerClave(id, clave) {
      await preparar();
      const u = cuenta(id);
      if (clave.length < 10) throw invalido("clave", CLAVE_CORTA);
      return guardar(id, {}, `Contraseña de ${u.nombre} restablecida; sus sesiones abiertas se cerraron.`);
    },
    async listarCargos(signal) {
      await preparar(signal);
      return [...cargos].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    },
    async crearCargo(nombre) {
      await preparar();
      const limpio = nombre.split(/\s+/).filter(Boolean).join(" ").slice(0, 60);
      const problema = problemaDeCargo(limpio);
      if (problema) throw invalido("nombre", problema);
      const repetido = cargos.find((c) => c.nombre.toLocaleLowerCase("es") === limpio.toLocaleLowerCase("es"));
      if (repetido) throw invalido("nombre", `Ya existe el cargo «${repetido.nombre}».`);
      const nuevo = { id: Math.max(0, ...cargos.map((c) => c.id)) + 1, nombre: limpio, activo: true, personas: 0 };
      cargos.push(nuevo);
      return nuevo;
    },
    async cambiarCargoCatalogo(id, { nombre, activo }) {
      await preparar();
      const indice = cargos.findIndex((c) => c.id === id);
      if (indice < 0) throw new ErrorDeAplicacion("no_encontrado");
      let cargo = cargos[indice]!;
      if (nombre !== undefined) {
        const limpio = nombre.split(/\s+/).filter(Boolean).join(" ").slice(0, 60);
        const problema = problemaDeCargo(limpio);
        if (problema) throw invalido("nombre", problema);
        if (cargos.some((c) => c.id !== id && c.nombre.toLocaleLowerCase("es") === limpio.toLocaleLowerCase("es"))) {
          throw invalido("nombre", `Ya existe el cargo «${limpio}».`);
        }
        cargo = { ...cargo, nombre: limpio };
        for (const [i, u] of usuarios.entries()) if (u.cargo?.id === id) usuarios[i] = { ...u, cargo: { id, nombre: limpio } };
      }
      if (activo !== undefined) cargo = { ...cargo, activo };
      cargos[indice] = cargo;
      return cargo;
    },
  };
}
