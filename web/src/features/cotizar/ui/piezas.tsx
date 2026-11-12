import Link from "next/link";
import type { ReactNode } from "react";
import { clasesBoton } from "@/shared/ui/boton";

/*
 * Piezas de interfaz que el anexo de diseño pone en `shared/ui` (las crea web-admin en su rama).
 * Mismos nombres y propiedades que allá, con los mismos tokens: al unir se reemplazan por las compartidas.
 */

export function Migas({ items }: { items: readonly { texto: string; href?: string }[] }) {
  return (
    <nav aria-label="Migas de pan" className="text-sm text-texto-secundario">
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((item, i) => (
          <li key={`${item.texto}-${i}`} className="flex items-center gap-1">
            {i > 0 ? <span aria-hidden="true">/</span> : null}
            {item.href ? (
              <Link href={item.href}>{item.texto}</Link>
            ) : (
              <span aria-current="page">{item.texto}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function EncabezadoPagina({
  titulo,
  descripcion,
  migas,
  accion,
  idTitulo,
}: {
  titulo: ReactNode;
  descripcion?: ReactNode;
  migas?: readonly { texto: string; href?: string }[];
  accion?: ReactNode;
  idTitulo?: string;
}) {
  return (
    <header className="flex flex-col gap-2">
      {migas ? <Migas items={migas} /> : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 id={idTitulo} className="text-3xl font-bold leading-tight">
            {titulo}
          </h1>
          {descripcion ? <div className="max-w-prose text-texto-secundario">{descripcion}</div> : null}
        </div>
        {accion}
      </div>
    </header>
  );
}

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
    <div className="flex flex-col items-start gap-3 rounded-tarjeta border border-dashed border-borde-campo bg-superficie p-6">
      <h2 className="text-xl font-bold">{titulo}</h2>
      {children ? <div className="max-w-prose text-texto-secundario">{children}</div> : null}
      {accion ? (
        <Link href={accion.href} className={clasesBoton("primario")}>
          {accion.texto}
        </Link>
      ) : null}
    </div>
  );
}

/** Bloques grises con la forma de lo que viene; el texto lo anuncia a quien no ve la pantalla. */
export function EsqueletoDetalle({ texto }: { texto: string }) {
  return (
    <div role="status" className="flex flex-col gap-4" aria-busy="true">
      <span className="sr-only">{texto}</span>
      <p aria-hidden="true" className="text-texto-secundario">
        {texto}
      </p>
      <div aria-hidden="true" className="flex flex-col gap-3 motion-safe:animate-pulse">
        <div className="h-8 w-2/3 rounded-lg bg-neutro-suave" />
        <div className="h-4 w-1/2 rounded-lg bg-neutro-suave" />
        <div className="h-28 rounded-tarjeta bg-neutro-suave" />
        <div className="h-28 rounded-tarjeta bg-neutro-suave" />
      </div>
    </div>
  );
}

/** Etiqueta corta junto a un dato (origen del precio, «Google», «Recomendada»). Siempre con texto. */
export function Marca({
  tono = "neutro",
  children,
}: {
  tono?: "marca" | "exito" | "aviso" | "neutro";
  children: ReactNode;
}) {
  const estilos = {
    marca: "border-marca bg-marca-suave text-marca",
    exito: "border-exito bg-exito-suave text-exito",
    aviso: "border-aviso bg-aviso-suave text-aviso",
    neutro: "border-neutro bg-neutro-suave text-neutro",
  } as const;
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-bold ${estilos[tono]}`}>
      {children}
    </span>
  );
}
