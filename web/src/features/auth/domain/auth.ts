/** El permiso: qué puede hacer la persona en la plataforma. */
export type Rol = "colaborador" | "gestor" | "admin";

export interface Persona {
  readonly id: number;
  readonly codigo: string;
  readonly nombre: string;
  readonly rol: Rol;
  readonly correo: string;
  /** Qué hace la persona en la empresa («Pilotaje de dron»…). No da permisos. */
  readonly cargo: string | null;
  /** La sesión es de un entorno de demostración (lo dice el servidor): la barra lo indica. */
  readonly demostracion?: boolean;
}

/** Sesión del navegador. La identidad la decide el servidor a partir de la cookie. */
export interface AuthRepository {
  entrar(correo: string, clave: string): Promise<Persona>;
  /** Persona con sesión, o `null` si no hay sesión o venció. */
  quienSoy(signal?: AbortSignal): Promise<Persona | null>;
  salir(): Promise<void>;
}

const BASE_INTERNA = "http://interno.invalid";

/**
 * Ruta interna a la que volver después de entrar; descarta destinos externos. El navegador quita tabuladores y saltos
 * de línea y lee «\» como «/»: «/\t/sitio» acaba en «//sitio», que es otro origen. Por eso se rechazan los espacios,
 * los caracteres de control y la barra invertida, y se comprueba que la ruta no cambie de origen.
 */
export function destinoSeguro(volver: string | null | undefined, porDefecto = "/viajes"): string {
  if (!volver || !volver.startsWith("/") || volver.startsWith("//")) return porDefecto;
  if ([...volver].some((c) => c.charCodeAt(0) <= 0x20 || c.charCodeAt(0) === 0x7f || c === "\\")) return porDefecto;
  if (new URL(volver, BASE_INTERNA).origin !== BASE_INTERNA) return porDefecto;
  if (volver.startsWith("/entrar")) return porDefecto;
  return volver;
}
