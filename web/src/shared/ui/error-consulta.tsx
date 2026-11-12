import Link from "next/link";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { Boton } from "./boton";
import { Alerta } from "./estado";

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
          Por seguridad cerramos tu sesión. <Link href="/entrar">Entra de nuevo</Link> para
          continuar.
        </p>
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
        <p className="mt-1 text-sm text-texto-secundario">Referencia: {error.idPeticion}</p>
      ) : null}
      {onReintentar ? (
        <Boton variante="secundario" className="mt-3" onClick={onReintentar}>
          Reintentar
        </Boton>
      ) : null}
    </Alerta>
  );
}
