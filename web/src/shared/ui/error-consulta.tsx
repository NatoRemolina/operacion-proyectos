import Link from "next/link";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { Boton } from "./boton";
import { Alerta } from "./estado";

/** Ruta actual, para volver a ella después de entrar de nuevo. */
function rutaActual(): string {
  if (typeof window === "undefined") return "";
  return `${window.location.pathname}${window.location.search}`;
}

/** Error de una lectura, con la salida que corresponde a cada caso. */
export function ErrorConsulta({
  error,
  onReintentar,
  volverA,
}: {
  error: ErrorDeAplicacion;
  onReintentar?: () => void;
  volverA?: { href: string; texto: string };
}) {
  if (error.tipo === "sesion_vencida") {
    return (
      <Alerta tono="aviso" titulo="Tu sesión venció" rol="alert">
        <p>
          Por seguridad cerramos tu sesión.{" "}
          <Link href={rutaActual() ? `/entrar?volver=${encodeURIComponent(rutaActual())}` : "/entrar"}>
            Entra de nuevo
          </Link>{" "}
          y volverás a esta misma página.
        </p>
      </Alerta>
    );
  }
  if (error.tipo === "prohibido") {
    return (
      <Alerta tono="neutro" titulo="Esta página no está disponible con tu permiso" rol="alert">
        <p>La ve administración. Si crees que deberías verla, pídeselo a quien administra la plataforma.</p>
        {volverA ? (
          <p className="mt-2">
            <Link href={volverA.href}>{volverA.texto}</Link>
          </p>
        ) : null}
      </Alerta>
    );
  }
  if (error.tipo === "no_encontrado") {
    return (
      <Alerta tono="neutro" titulo="No encontramos esta información" rol="alert">
        <p>No existe o no tienes acceso a ella.</p>
        {volverA ? (
          <p className="mt-2">
            <Link href={volverA.href}>{volverA.texto}</Link>
          </p>
        ) : null}
      </Alerta>
    );
  }
  return (
    <Alerta tono="error" titulo="No se pudo cargar la información" rol="alert">
      <p>{error.message}</p>
      {error.idPeticion ? (
        <p className="mt-1 text-xs text-texto-secundario">Referencia: {error.idPeticion}</p>
      ) : null}
      {onReintentar ? (
        <Boton variante="secundario" className="mt-3" onClick={onReintentar}>
          Reintentar
        </Boton>
      ) : null}
    </Alerta>
  );
}
