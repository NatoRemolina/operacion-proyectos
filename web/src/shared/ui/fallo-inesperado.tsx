"use client";

import Link from "next/link";
import { esErrorDeAplicacion } from "@/shared/domain/errores";
import { Boton, clasesBoton } from "./boton";
import { Alerta } from "./estado";

const MENSAJE_GENERICO =
  "La página tuvo un problema inesperado. Si vuelve a pasar, comparte la referencia con administración.";

/**
 * Qué mostrar de lo que llegó a una frontera de error. Un error de la API trae su mensaje claro y el `request_id`; uno
 * del servidor de la web, solo su identificador (`digest`): su texto puede traer detalles internos y no se muestra.
 */
export function datosDelFallo(error: unknown): { mensaje: string; referencia: string | null } {
  if (esErrorDeAplicacion(error)) return { mensaje: error.message, referencia: error.idPeticion };
  const digest =
    error instanceof Error && "digest" in error && typeof error.digest === "string" ? error.digest : null;
  return { mensaje: MENSAJE_GENERICO, referencia: digest };
}

/** Contenido de `error.tsx` y `global-error.tsx`: mensaje, referencia para administración y cómo seguir. */
export function FalloInesperado({ error, retry }: { error: unknown; retry: () => void }) {
  const { mensaje, referencia } = datosDelFallo(error);
  return (
    <main id="contenido" className="mx-auto w-full max-w-contenido px-4 py-10">
      <div className="flex max-w-2xl flex-col gap-4">
        <h1 className="text-2xl font-extrabold">Algo falló al mostrar esta página</h1>
        <Alerta tono="error" rol="alert" titulo="No se pudo mostrar">
          <p>{mensaje}</p>
          {referencia ? <p className="mt-1 text-sm text-texto-secundario">Referencia: {referencia}</p> : null}
        </Alerta>
        <div className="flex flex-wrap gap-2">
          <Boton onClick={retry}>Reintentar</Boton>
          <Link href="/viajes" className={clasesBoton("secundario")}>
            Ir a mis viajes
          </Link>
        </div>
      </div>
    </main>
  );
}
