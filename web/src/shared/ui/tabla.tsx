"use client";

import Link from "next/link";
import { useState, type Key, type ReactNode } from "react";

export interface Columna<T> {
  clave: string;
  encabezado: string;
  celda: (fila: T) => ReactNode;
  /** Las cifras se alinean a la derecha. */
  alinear?: "inicio" | "fin";
  /** La columna que nombra la fila: lleva el enlace y es el título de la tarjeta en celular. */
  principal?: boolean;
}

/**
 * Tabla con encabezado fijo y fila clicable (el enlace de la columna principal cubre la fila).
 * En celular la misma información se muestra como tarjetas, una por fila.
 */
export function Tabla<T>({
  titulo,
  tituloVisible = false,
  filas,
  columnas,
  claveFila,
  hrefFila,
  acciones,
  encabezadoAcciones = "Acción",
}: {
  titulo: string;
  tituloVisible?: boolean;
  filas: readonly T[];
  columnas: readonly Columna<T>[];
  claveFila: (fila: T) => Key;
  hrefFila?: (fila: T) => string | null;
  acciones?: (fila: T) => ReactNode;
  encabezadoAcciones?: string;
}) {
  // El borde bajo el encabezado fijo aparece solo cuando hay contenido desplazado debajo.
  const [desplazada, setDesplazada] = useState(false);
  const principal = columnas.find((c) => c.principal) ?? columnas[0]!;
  const resto = columnas.filter((c) => c !== principal);
  const compacta = !acciones && resto.length === 1 && resto[0]!.alinear === "fin";

  function contenidoPrincipal(fila: T, cubrirFila: boolean) {
    const href = hrefFila?.(fila) ?? null;
    if (!href) return principal.celda(fila);
    return (
      <Link
        href={href}
        className={`font-semibold ${cubrirFila ? "after:absolute after:inset-0 after:content-['']" : ""}`}
      >
        {principal.celda(fila)}
      </Link>
    );
  }

  return (
    <>
      <div
        className="hidden max-h-128 overflow-auto rounded-tarjeta border border-linea bg-superficie md:block"
        onScroll={(e) => setDesplazada(e.currentTarget.scrollTop > 0)}
      >
        <table className="w-full border-collapse text-left">
          <caption className={tituloVisible ? "px-4 pt-4 text-left text-lg font-bold" : "sr-only"}>{titulo}</caption>
          <thead className={`sticky top-0 z-10 bg-fondo ${desplazada ? "shadow-tarjeta" : ""}`}>
            <tr>
              {columnas.map((c) => (
                <th
                  key={c.clave}
                  scope="col"
                  className={`px-4 py-3 text-xs font-semibold uppercase tracking-wide text-texto-secundario ${
                    c.alinear === "fin" ? "text-right" : ""
                  }`}
                >
                  {c.encabezado}
                </th>
              ))}
              {acciones ? (
                <th
                  scope="col"
                  className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-texto-secundario"
                >
                  {encabezadoAcciones}
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => (
              <tr
                key={claveFila(fila)}
                className={`relative border-b border-linea last:border-b-0 ${hrefFila?.(fila) ? "hover:bg-neutro-suave" : ""}`}
              >
                {columnas.map((c) => (
                  <td
                    key={c.clave}
                    className={`px-4 py-3 align-top ${c.alinear === "fin" ? "text-right tabular-nums whitespace-nowrap" : ""}`}
                  >
                    {c === principal ? contenidoPrincipal(fila, true) : c.celda(fila)}
                  </td>
                ))}
                {acciones ? <td className="relative z-10 px-4 py-3 align-top">{acciones(fila)}</td> : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {compacta ? (
        // Concepto e importe: en celular basta una lista con el importe a la derecha, sin repetir la etiqueta.
        <ul
          aria-label={titulo}
          className="flex flex-col rounded-tarjeta border border-linea bg-superficie px-4 shadow-tarjeta md:hidden"
        >
          {filas.map((fila) => (
            <li
              key={claveFila(fila)}
              className="flex items-start justify-between gap-4 border-b border-linea py-3 last:border-b-0"
            >
              <span className="min-w-0">{contenidoPrincipal(fila, false)}</span>
              <span className="whitespace-nowrap font-semibold tabular-nums">{resto[0]!.celda(fila)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <ul aria-label={titulo} className="flex flex-col gap-3 md:hidden">
          {filas.map((fila) => (
            <li key={claveFila(fila)} className="rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta">
              <p className="text-base">{contenidoPrincipal(fila, false)}</p>
              <dl className="mt-2 flex flex-col gap-1 text-sm">
                {resto.map((c) => (
                  <div key={c.clave} className="flex justify-between gap-4">
                    <dt className="text-texto-secundario">{c.encabezado}</dt>
                    <dd className={`text-right ${c.alinear === "fin" ? "font-semibold tabular-nums" : ""}`}>
                      {c.celda(fila)}
                    </dd>
                  </div>
                ))}
              </dl>
              {acciones ? <div className="mt-3 flex flex-wrap gap-2">{acciones(fila)}</div> : null}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
