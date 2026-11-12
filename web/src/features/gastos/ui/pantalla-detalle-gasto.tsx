"use client";

import Link from "next/link";
import { Cargando } from "@/shared/ui/estado";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { useGasto, useUrlOriginal } from "../application/gastos";
import { DetalleGasto } from "./detalle-gasto";
import { JustificacionGasto } from "./justificacion-gasto";

export function PantallaDetalleGasto({ id }: { id: number }) {
  const consulta = useGasto(id);
  const urlOriginal = useUrlOriginal(consulta.data?.documento_id ?? null);
  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <p>
        <Link href="/gastos" className="inline-flex min-h-11 items-center">
          ← Volver a mis gastos
        </Link>
      </p>
      {consulta.data ? (
        <>
          <DetalleGasto gasto={consulta.data} urlOriginal={urlOriginal} />
          <JustificacionGasto gasto={consulta.data} />
        </>
      ) : consulta.error ? (
        <>
          <h1 className="text-2xl font-extrabold">Detalle del gasto</h1>
          <ErrorConsulta
            error={consulta.error}
            onReintentar={() => void consulta.refetch()}
            volverA={{ href: "/gastos", texto: "Volver a mis gastos" }}
          />
        </>
      ) : (
        <Cargando texto="Cargando el gasto…" />
      )}
    </div>
  );
}
