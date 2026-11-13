"use client";

import Link from "next/link";
import { useState } from "react";
import { useViajes } from "@/features/viajes/application/viajes";
import { usePermiso } from "@/shared/application/identidad";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { CampoSelector } from "@/shared/ui/campo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { EstadoVacio } from "@/shared/ui/estado-vacio";
import { PRESIONAR } from "@/shared/ui/movimiento";
import { useGastos } from "../application/gastos";
import type { EstadoGasto } from "../domain/gastos";
import { ID_PANEL_EXCEL, PanelExcelContable } from "./excel-contable";
import { ListaGastos } from "./lista-gastos";

const FILTROS: readonly { estado?: EstadoGasto; texto: string }[] = [
  { texto: "Todos" },
  { estado: "revision", texto: "En revisión" },
  { estado: "aprobado_auto", texto: "Aprobados al cargar" },
  { estado: "aprobado", texto: "Aprobados en revisión" },
  { estado: "rechazado", texto: "Rechazados" },
];

export function PantallaGastos({ estado: estadoInicial, viajeId: viajeInicial }: { estado?: EstadoGasto; viajeId?: number } = {}) {
  const permiso = usePermiso();
  const esAdmin = permiso === "admin";
  const [estado, setEstado] = useState<EstadoGasto | undefined>(estadoInicial);
  const [viajeId, setViajeId] = useState<number | undefined>(viajeInicial);
  const [excelAbierto, setExcelAbierto] = useState(false);
  const consulta = useGastos({ ...(estado ? { estado } : {}), ...(viajeId ? { viajeId } : {}) });
  const viajes = useViajes();
  const filtrando = Boolean(estado || viajeId);

  return (
    <div className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Operaciones" }, { texto: permiso === "colaborador" ? "Mis gastos" : "Gastos" }]}
        titulo={permiso === "colaborador" ? "Mis gastos" : "Gastos"}
        descripcion={
          esAdmin
            ? "Todos los gastos. Los que están en revisión esperan tu decisión."
            : permiso === "gestor"
              ? "Los tuyos y los de los proyectos que gestionas."
              : "Tus recibos con su estado y lo que sigue en cada uno."
        }
        accion={
          <>
            <Boton
              variante="secundario"
              aria-expanded={excelAbierto}
              aria-controls={excelAbierto ? ID_PANEL_EXCEL : undefined}
              onClick={() => setExcelAbierto((a) => !a)}
            >
              Excel contable
            </Boton>
            <Link href="/gastos/nuevo" className={clasesBoton("primario")}>
              Cargar recibo
            </Link>
          </>
        }
      />

      {excelAbierto ? <PanelExcelContable permiso={permiso} /> : null}

      {/* Los estados en una fila propia y el viaje debajo: con los dos lado a lado, el último estado quedaba solo. */}
      <div className="flex flex-col gap-3">
        <div role="group" aria-label="Filtrar por estado" className="flex flex-wrap gap-2">
          {FILTROS.map((f) => {
            const activo = f.estado === estado;
            return (
              <button
                key={f.texto}
                type="button"
                aria-pressed={activo}
                onClick={() => setEstado(f.estado)}
                // 44 px de alto en el celular; en escritorio, con puntero preciso, más compactos para caber en una fila.
                className={`inline-flex min-h-11 items-center rounded-full border px-3.5 text-sm font-semibold transition-colors duration-150 md:min-h-9 ${PRESIONAR} ${
                  activo
                    ? "border-marca bg-marca-suave text-marca"
                    : "border-linea bg-superficie text-texto hover:border-borde-campo"
                }`}
              >
                {f.texto}
              </button>
            );
          })}
        </div>
        <div className="sm:w-64">
          <CampoSelector
            id="filtro-viaje"
            etiqueta="Viaje"
            value={viajeId ? String(viajeId) : ""}
            onChange={(e) => setViajeId(e.target.value ? Number(e.target.value) : undefined)}
          >
            <option value="">Todos los viajes</option>
            {viajes.viajes.map((v) => (
              <option key={v.id} value={String(v.id)}>
                {v.codigo} · {v.origen} → {v.destino}
              </option>
            ))}
          </CampoSelector>
        </div>
      </div>

      {consulta.isPending ? (
        <EsqueletoLista texto="Cargando los gastos…" />
      ) : consulta.error && consulta.gastos.length === 0 ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : consulta.gastos.length === 0 ? (
        filtrando ? (
          <p className="rounded-tarjeta border border-linea bg-superficie p-4 text-texto-secundario">
            No hay gastos con ese filtro.
          </p>
        ) : (
          <EstadoVacio titulo="Aún no tienes gastos" accion={{ href: "/gastos/nuevo", texto: "Cargar mi primer recibo" }}>
            Toma una foto del recibo o súbelo en PDF: lo leemos y lo asociamos a tu viaje.
          </EstadoVacio>
        )
      ) : (
        <>
          <ListaGastos gastos={consulta.gastos} esAdmin={esAdmin} />
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
    </div>
  );
}
