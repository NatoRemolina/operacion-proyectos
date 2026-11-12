import Link from "next/link";
import type { ReactNode } from "react";
import { clasesBoton } from "./boton";

/** Vista sin datos: qué significa y qué hacer ahora. */
export function EstadoVacio({
  titulo,
  children,
  accion,
}: {
  titulo: string;
  children?: ReactNode;
  accion?: { href: string; texto: string };
}) {
  return (
    <section className="flex flex-col items-start gap-2 rounded-tarjeta border border-dashed border-borde-campo bg-superficie p-6">
      <h2 className="text-lg font-bold">{titulo}</h2>
      {children ? <div className="text-texto-secundario">{children}</div> : null}
      {accion ? (
        <Link href={accion.href} className={clasesBoton("primario", "mt-2")}>
          {accion.texto}
        </Link>
      ) : null}
    </section>
  );
}
