"use client";

import Link from "next/link";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { Cargando } from "@/shared/ui/estado";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { useViajes } from "../application/viajes";
import { ListaViajes } from "./lista-viajes";
import { ResumenViajeEnCurso } from "./resumen-viaje-en-curso";

export function PantallaViajes() {
  const consulta = useViajes();
  const enCurso = consulta.viajes.find((v) => v.en_curso);
  return (
    <section aria-labelledby="titulo-viajes" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id="titulo-viajes" className="text-3xl font-bold">
          Mis viajes
        </h1>
        <Link href="/gastos/nuevo" className={clasesBoton("primario")}>
          Cargar un gasto
        </Link>
      </div>
      {consulta.isPending ? (
        <Cargando texto="Cargando tus viajes…" />
      ) : consulta.error && consulta.viajes.length === 0 ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : consulta.viajes.length === 0 ? (
        <p className="rounded-tarjeta border border-linea bg-superficie p-4">
          Aún no tienes viajes. Cuando administración apruebe uno, aparecerá aquí.
        </p>
      ) : (
        <>
          {enCurso ? <ResumenViajeEnCurso viaje={enCurso} /> : null}
          <h2 className="mt-2 text-lg font-bold">Todos mis viajes</h2>
          <ListaViajes viajes={consulta.viajes} />
          {consulta.hasNextPage ? (
            <Boton
              variante="secundario"
              onClick={() => void consulta.fetchNextPage()}
              disabled={consulta.isFetchingNextPage}
            >
              {consulta.isFetchingNextPage ? "Cargando…" : "Ver más viajes"}
            </Boton>
          ) : null}
        </>
      )}
    </section>
  );
}
