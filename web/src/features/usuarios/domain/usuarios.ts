import type { Permiso } from "@/shared/domain/navegacion";
import type { OpcionesListado, Pagina } from "@/shared/domain/tipos";

export interface Referencia {
  readonly id: number;
  readonly nombre: string;
}

export interface Usuario {
  readonly id: number;
  readonly codigo: string;
  readonly correo: string;
  readonly nombre: string;
  readonly rol: Permiso;
  readonly rol_texto: string;
  /** Qué hace en la empresa. No da permisos. */
  readonly cargo: Referencia | null;
  /** Proyectos que gestiona (solo cuentan con el permiso de gestor). */
  readonly proyectos: readonly Referencia[];
  readonly activo: boolean;
  readonly telegram: { readonly vinculado: boolean; readonly usuario: string | null };
  readonly ultima_sesion: string | null;
  readonly creado: string | null;
}

export interface ResultadoUsuario {
  readonly usuario: Usuario;
  readonly mensaje: string;
}

export interface Cargo {
  readonly id: number;
  readonly nombre: string;
  readonly activo: boolean;
  readonly personas: number;
}

/** La contraseña inicial la escribe administración; nunca vuelve en una respuesta. */
export interface NuevaCuenta {
  readonly correo: string;
  readonly nombre: string;
  readonly rol: Permiso;
  readonly clave: string;
  readonly cargo_id: number | null;
}

export type CampoCuenta = keyof NuevaCuenta;

export interface UsuariosRepository {
  /** Todas las cuentas, activas o no, la más reciente primero. Solo administración. */
  listar(opciones: OpcionesListado, signal?: AbortSignal): Promise<Pagina<Usuario>>;
  crear(datos: NuevaCuenta): Promise<ResultadoUsuario>;
  cambiarRol(id: number, rol: Permiso): Promise<ResultadoUsuario>;
  cambiarEstado(id: number, activo: boolean): Promise<ResultadoUsuario>;
  cambiarCargo(id: number, cargoId: number | null): Promise<ResultadoUsuario>;
  asignarProyectos(id: number, proyectosIds: readonly number[]): Promise<ResultadoUsuario>;
  restablecerClave(id: number, clave: string): Promise<ResultadoUsuario>;
  listarCargos(signal?: AbortSignal): Promise<readonly Cargo[]>;
  crearCargo(nombre: string): Promise<Cargo>;
  cambiarCargoCatalogo(id: number, cambio: { nombre?: string; activo?: boolean }): Promise<Cargo>;
}

export const PERMISOS: readonly { valor: Permiso; texto: string }[] = [
  { valor: "colaborador", texto: "colaborador" },
  { valor: "gestor", texto: "gestor de proyecto" },
  { valor: "admin", texto: "administrador" },
];

export const CLAVE_MINIMA = 10;
export const CLAVE_CORTA = "La contraseña debe tener al menos 10 caracteres.";

/** Qué corregir antes de enviar. Las mismas condiciones que el servidor (el correo repetido lo dice el servidor). */
export function problemasDeCuenta(datos: NuevaCuenta): Partial<Record<CampoCuenta, string>> {
  const problemas: Partial<Record<CampoCuenta, string>> = {};
  if (!datos.correo.includes("@")) problemas.correo = "Escribe un correo válido.";
  if (datos.clave.length < CLAVE_MINIMA) problemas.clave = CLAVE_CORTA;
  return problemas;
}

/** El nombre de un cargo necesita al menos 3 letras, como en el servidor. */
export function problemaDeCargo(nombre: string): string | null {
  const letras = [...nombre].filter((c) => /\p{L}/u.test(c)).length;
  return letras < 3 ? "El nombre del cargo necesita al menos 3 letras." : null;
}
