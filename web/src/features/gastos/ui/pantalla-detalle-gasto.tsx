"use client";

import { RevisionGasto } from "@/features/administracion/ui/revision-gasto";
import { usePermiso } from "@/shared/application/identidad";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoDetalle } from "@/shared/ui/esqueleto";
import { Migas } from "@/shared/ui/migas";
import { useGasto, useUrlOriginal } from "../application/gastos";
import { DetalleGasto } from "./detalle-gasto";
import { JustificacionGasto } from "./justificacion-gasto";

export function PantallaDetalleGasto({ id }: { id: number }) {
  const consulta = useGasto(id);
  const permiso = usePermiso();
  const urlOriginal = useUrlOriginal(consulta.data?.documento_id ?? null);
  const gasto = consulta.data;
  const lista = permiso === "colaborador" ? "Mis gastos" : "Gastos";
  const migas = [{ texto: lista, href: "/gastos" }, { texto: gasto?.comercio ?? "Detalle del gasto" }];

  if (!gasto) {
    return (
      <div className="flex max-w-2xl flex-col gap-4">
        <EncabezadoPagina migas={migas} titulo="Detalle del gasto" />
        {consulta.error ? (
          <ErrorConsulta
            error={consulta.error}
            onReintentar={() => void consulta.refetch()}
            volverA={{ href: "/gastos", texto: `Volver a ${lista.toLowerCase()}` }}
          />
        ) : (
          <EsqueletoDetalle texto="Cargando el gasto…" />
        )}
      </div>
    );
  }

  // Administración revisa aquí mismo lo que está en revisión: recibo, lectura y decisión.
  if (permiso === "admin" && gasto.estado === "revision") {
    return <RevisionGasto gasto={gasto} urlOriginal={urlOriginal} migas={migas} />;
  }

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Migas items={migas} />
      <DetalleGasto gasto={gasto} urlOriginal={urlOriginal} />
      <JustificacionGasto gasto={gasto} />
    </div>
  );
}
