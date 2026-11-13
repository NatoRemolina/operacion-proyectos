"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Boton } from "@/shared/ui/boton";
import { CampoSelector, CampoTexto } from "@/shared/ui/campo";
import { consultaDeDireccion, hayFiltros, type FiltrosTablero } from "../domain/kpis";

/**
 * Proyecto y fechas, como en la pantalla de hoy. Se aplican cambiando la dirección: un tablero filtrado
 * se puede compartir o recargar. `extra` conserva otros parámetros (por ejemplo, la pestaña de Monitoreo).
 */
export function FiltrosTablero({
  ruta,
  filtros,
  proyectos,
  extra = {},
}: {
  ruta: string;
  filtros: FiltrosTablero;
  proyectos: readonly { readonly id: number; readonly nombre: string }[];
  extra?: Record<string, string>;
}) {
  const router = useRouter();
  const [proyecto, setProyecto] = useState(filtros.proyecto_id ? String(filtros.proyecto_id) : "");
  const [desde, setDesde] = useState(filtros.desde ?? "");
  const [hasta, setHasta] = useState(filtros.hasta ?? "");
  const rangoInvalido = desde !== "" && hasta !== "" && desde > hasta;

  function aplicar(e: FormEvent) {
    e.preventDefault();
    if (rangoInvalido) return;
    router.push(`${ruta}${consultaDeDireccion({ ...extra, proyecto: proyecto || null, desde: desde || null, hasta: hasta || null })}`);
  }

  return (
    <form
      onSubmit={aplicar}
      aria-label="Filtros"
      className="grid grid-cols-1 items-end gap-3 rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta sm:grid-cols-2 lg:grid-cols-4"
    >
      <CampoSelector id="filtro-proyecto" etiqueta="Proyecto" value={proyecto} onChange={(e) => setProyecto(e.target.value)}>
        <option value="">Todos</option>
        {proyectos.map((p) => (
          <option key={p.id} value={p.id}>
            {p.nombre}
          </option>
        ))}
      </CampoSelector>
      <CampoTexto id="filtro-desde" etiqueta="Desde" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
      <CampoTexto
        id="filtro-hasta"
        etiqueta="Hasta"
        type="date"
        value={hasta}
        onChange={(e) => setHasta(e.target.value)}
        error={rangoInvalido ? "«Hasta» no puede ser antes de «Desde»." : null}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Boton type="submit">Aplicar</Boton>
        {hayFiltros(filtros) ? (
          <Link href={`${ruta}${consultaDeDireccion(extra)}`} className="inline-flex min-h-11 items-center">
            Quitar filtros
          </Link>
        ) : null}
      </div>
    </form>
  );
}
