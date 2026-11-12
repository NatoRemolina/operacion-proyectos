export type Rol = "piloto" | "gestor" | "admin";

export interface Persona {
  readonly id: number;
  readonly codigo: string;
  readonly nombre: string;
  readonly rol: Rol;
  readonly correo: string;
}

/** Sesión del navegador. La identidad la decide el servidor a partir de la cookie. */
export interface AuthRepository {
  entrar(correo: string, clave: string): Promise<Persona>;
  /** Persona con sesión, o `null` si no hay sesión o venció. */
  quienSoy(signal?: AbortSignal): Promise<Persona | null>;
  salir(): Promise<void>;
}

/** Ruta interna a la que volver después de entrar; descarta destinos externos. */
export function destinoSeguro(volver: string | null | undefined, porDefecto = "/viajes"): string {
  if (!volver || !volver.startsWith("/") || volver.startsWith("//") || volver.startsWith("/\\")) {
    return porDefecto;
  }
  if (volver.startsWith("/entrar")) return porDefecto;
  return volver;
}
