/**
 * Errores de aplicación estables. La interfaz decide qué mostrar a partir del `tipo`;
 * nunca depende del código HTTP ni de la forma de la respuesta del servidor.
 */
export type TipoError =
  | "sesion_vencida"
  | "credenciales"
  | "demasiados_intentos"
  | "prohibido"
  | "no_encontrado"
  | "conflicto"
  | "demasiado_grande"
  | "tipo_no_admitido"
  | "validacion"
  | "autoaprobacion"
  | "estado_invalido"
  | "precio_por_confirmar"
  | "cambio_ajeno"
  | "red"
  | "contrato"
  | "servidor";

const MENSAJES: Record<TipoError, string> = {
  sesion_vencida: "Tu sesión venció. Entra de nuevo para continuar.",
  credenciales: "El correo o la contraseña no son correctos.",
  demasiados_intentos: "Hubo demasiados intentos. Espera unos minutos y vuelve a intentarlo.",
  prohibido: "No tienes permiso para hacer esta operación.",
  no_encontrado: "No encontramos lo que buscas o no tienes acceso.",
  conflicto: "Ese envío ya se usó con otro archivo.",
  demasiado_grande: "El archivo pesa más de 4,5 MB.",
  tipo_no_admitido: "Ese tipo de archivo no se admite. Usa una foto (JPG, PNG o WebP) o un PDF.",
  validacion: "Hay datos que no son válidos.",
  autoaprobacion: "Nadie aprueba lo suyo: lo decide otra persona de administración.",
  estado_invalido: "El estado cambió y esa acción ya no aplica. Recarga para ver cómo está.",
  precio_por_confirmar: "El precio del vuelo cambió: confírmalo para aprobar.",
  cambio_ajeno: "Otra persona lo cambió mientras lo veías. Cargamos lo último para que lo revises de nuevo.",
  red: "No hubo conexión con el servidor.",
  contrato: "El servidor respondió algo inesperado.",
  servidor: "Algo falló en el servidor. Ya quedó registrado.",
};

export class ErrorDeAplicacion extends Error {
  readonly tipo: TipoError;
  readonly campos: Readonly<Record<string, string>>;
  readonly idPeticion: string | null;

  constructor(
    tipo: TipoError,
    opciones: { mensaje?: string; campos?: Record<string, string>; idPeticion?: string | null } = {},
  ) {
    super(opciones.mensaje ?? MENSAJES[tipo]);
    this.name = "ErrorDeAplicacion";
    this.tipo = tipo;
    this.campos = opciones.campos ?? {};
    this.idPeticion = opciones.idPeticion ?? null;
  }
}

export function esErrorDeAplicacion(error: unknown): error is ErrorDeAplicacion {
  return error instanceof ErrorDeAplicacion;
}

/** Normaliza cualquier fallo a un error de aplicación para que la interfaz no adivine. */
export function comoErrorDeAplicacion(error: unknown): ErrorDeAplicacion {
  return esErrorDeAplicacion(error) ? error : new ErrorDeAplicacion("servidor");
}

export function mensajeDeError(tipo: TipoError): string {
  return MENSAJES[tipo];
}
