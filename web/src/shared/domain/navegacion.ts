/**
 * Menú de la zona privada declarado como datos: cada entrada dice qué permisos la ven.
 * Mostrar u ocultar una entrada es experiencia de uso; quien hace cumplir el permiso es la API.
 */

/** Los mismos valores que el `rol` de la sesión. */
export type Permiso = "colaborador" | "gestor" | "admin";

export const TEXTO_PERMISO: Record<Permiso, string> = {
  admin: "Administración",
  gestor: "Gestión de proyectos",
  colaborador: "Colaboración",
};

export interface EntradaMenu {
  readonly href: string;
  readonly texto: string;
  /** Texto corto para la barra inferior del celular. */
  readonly corto: string;
  /** Pantalla de la plataforma actual (fuera de esta web): se abre con un enlace normal. */
  readonly externa: boolean;
  /** Aparece en la barra inferior del celular. */
  readonly atajo: boolean;
}

interface Declaracion {
  readonly ruta: string;
  readonly texto: string;
  readonly corto: string;
  readonly permisos: readonly Permiso[];
  readonly externa?: boolean;
  readonly atajo?: boolean;
}

const TODOS: readonly Permiso[] = ["admin", "gestor", "colaborador"];

const MENU: readonly Declaracion[] = [
  { ruta: "/resumen", texto: "Resumen", corto: "Resumen", permisos: ["admin"], atajo: true },
  { ruta: "/cotizar", texto: "Cotizar viaje", corto: "Cotizar", permisos: TODOS, atajo: true },
  { ruta: "/viajes", texto: "Viajes", corto: "Viajes", permisos: TODOS, atajo: true },
  { ruta: "/gastos", texto: "Gastos", corto: "Gastos", permisos: TODOS, atajo: true },
  { ruta: "/kpis", texto: "KPIs", corto: "KPIs", permisos: ["admin"] },
  { ruta: "/monitoreo", texto: "Monitoreo", corto: "Monitoreo", permisos: ["admin"] },
  { ruta: "/vuelos", texto: "Vuelos", corto: "Vuelos", permisos: ["admin"] },
  { ruta: "/reglas", texto: "Reglas y supuestos", corto: "Reglas", permisos: ["admin"] },
  // Mientras no existan en esta web, llevan a las pantallas actuales de la plataforma.
  { ruta: "/admin/proyectos", texto: "Proyectos", corto: "Proyectos", permisos: ["admin"], externa: true },
  { ruta: "/admin/usuarios", texto: "Usuarios", corto: "Usuarios", permisos: ["admin"], externa: true },
];

/**
 * Entradas que ve un permiso, en orden. `plataforma` es el origen de las pantallas actuales; sin él
 * no se ofrecen, porque el gateway solo lleva /api/v1 a la API y serían enlaces rotos.
 */
export function menuPara(permiso: Permiso, plataforma: string): EntradaMenu[] {
  return MENU.filter((d) => d.permisos.includes(permiso) && (!d.externa || plataforma)).map((d) => ({
    href: d.externa ? `${plataforma}${d.ruta}` : d.ruta,
    texto: d.texto,
    corto: d.corto,
    externa: d.externa ?? false,
    atajo: d.atajo ?? false,
  }));
}

/**
 * Dónde viven las pantallas actuales (Jinja). `NEXT_PUBLIC_PLATAFORMA_URL` manda; sin ella, el
 * origen de la API si es otro; si la API está en el mismo origen, queda vacío (no configurado).
 */
export function origenPantallasActuales(explicita: string | undefined, baseApi: string): string {
  const valor = (explicita ?? "").trim();
  if (valor) {
    let url: URL;
    try {
      url = new URL(valor);
    } catch {
      throw new Error(`NEXT_PUBLIC_PLATAFORMA_URL no es una URL válida: «${valor}».`);
    }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      throw new Error("NEXT_PUBLIC_PLATAFORMA_URL debe ser http(s) y sin credenciales.");
    }
    return valor.replace(/\/+$/, "");
  }
  try {
    const api = new URL(baseApi);
    return ["http:", "https:"].includes(api.protocol) ? api.origin : "";
  } catch {
    return "";
  }
}
