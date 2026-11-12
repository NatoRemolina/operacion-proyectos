"use client";

import Link from "next/link";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { Cargando } from "@/shared/ui/estado";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { useGastos } from "../application/gastos";
import { ListaGastos } from "./lista-gastos";

export function PantallaGastos() {
  const consulta = useGastos();
  return (
    <section aria-labelledby="titulo-gastos" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id="titulo-gastos" className="text-3xl font-bold">
          Mis gastos
        </h1>
        <Link href="/gastos/nuevo" className={clasesBoton("primario")}>
          Cargar un gasto
        </Link>
      </div>
      {consulta.isPending ? (
        <Cargando texto="Cargando tus gastos…" />
      ) : consulta.error && consulta.gastos.length === 0 ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : consulta.gastos.length === 0 ? (
        <p className="rounded-tarjeta border border-linea bg-superficie p-4">
          Aún no tienes gastos. <Link href="/gastos/nuevo">Envía tu primer recibo</Link>.
        </p>
      ) : (
        <>
          <ListaGastos gastos={consulta.gastos} />
          {consulta.hasNextPage ? (
            <Boton
              variante="secundario"
              onClick={() => void consulta.fetchNextPage()}
              disabled={consulta.isFetchingNextPage}
            >
              {consulta.isFetchingNextPage ? "Cargando…" : "Ver más gastos"}
            </Boton>
          ) : null}
        </>
      )}
    </section>
  );
}
