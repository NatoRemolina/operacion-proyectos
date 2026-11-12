import type { ReactNode } from "react";
import { Migas, type Miga } from "./migas";

/** Encabezado de página: dónde estás, el título (único h1), qué es y la acción principal. */
export function EncabezadoPagina({
  titulo,
  descripcion,
  migas,
  accion,
  idTitulo,
}: {
  titulo: ReactNode;
  descripcion?: ReactNode;
  migas?: readonly Miga[];
  accion?: ReactNode;
  idTitulo?: string;
}) {
  return (
    <header className="flex flex-col gap-1">
      {migas && migas.length ? <Migas items={migas} /> : null}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id={idTitulo} className="text-3xl font-extrabold">
          {titulo}
        </h1>
        {accion ? <div className="flex flex-wrap gap-2">{accion}</div> : null}
      </div>
      {/* Un div y no un p: la descripción puede traer listas o datos (por ejemplo, el resumen de una cotización). */}
      {descripcion ? <div className="max-w-prose text-texto-secundario">{descripcion}</div> : null}
    </header>
  );
}
