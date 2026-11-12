"use client";

import Link from "next/link";
import { DecisionViaje } from "@/features/administracion/ui/decision-viaje";
import { usePermiso } from "@/shared/application/identidad";
import { Boton, clasesBoton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { EstadoVacio } from "@/shared/ui/estado-vacio";
import { formatearDinero, formatearRango } from "@/shared/ui/formato";
import { useViajes } from "../application/viajes";
import type { EstadoViaje, ViajeResumen } from "../domain/viajes";
import { ListaViajes } from "./lista-viajes";
import { ResumenViajeEnCurso } from "./resumen-viaje-en-curso";

const FILTROS: readonly { estado?: EstadoViaje; texto: string }[] = [
  { texto: "Todos" },
  { estado: "pendiente_aprobacion", texto: "Por aprobar" },
  { estado: "aprobado", texto: "Aprobados" },
  { estado: "rechazado", texto: "Rechazados" },
  { estado: "cerrado", texto: "Cerrados" },
];

function Filtros({ activo }: { activo?: EstadoViaje }) {
  return (
    <nav aria-label="Filtrar por estado">
      <ul className="flex flex-wrap gap-2">
        {FILTROS.map((f) => {
          const actual = f.estado === activo;
          return (
            <li key={f.texto}>
              <Link
                href={f.estado ? `/viajes?estado=${f.estado}` : "/viajes"}
                aria-current={actual ? "page" : undefined}
                className={`inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-semibold no-underline ${
                  actual ? "border-marca bg-marca-suave text-marca" : "border-linea bg-superficie text-texto"
                }`}
              >
                {f.texto}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function TarjetaPorAprobar({ viaje }: { viaje: ViajeResumen }) {
  return (
    <li className="flex flex-col gap-3 rounded-tarjeta border border-linea bg-superficie p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-lg font-bold">
            <Link href={`/viajes/${viaje.id}`}>{viaje.codigo}</Link>
          </h3>
          <p className="font-semibold">{viaje.titular?.nombre ?? "Sin titular"}</p>
          <p className="text-sm text-texto-secundario">
            {viaje.origen} → {viaje.destino} · {formatearRango(viaje.ida, viaje.regreso)}
            {viaje.proyecto ? ` · ${viaje.proyecto.nombre}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-texto-secundario">Presupuesto</p>
          <p className="text-xl font-bold tabular-nums">{formatearDinero(viaje.presupuesto_usd, "USD")}</p>
          <Link href={`/viajes/${viaje.id}`} className="inline-flex min-h-11 items-center text-sm">
            Ver el desglose
          </Link>
        </div>
      </div>
      <DecisionViaje viaje={viaje} />
    </li>
  );
}

function PorAprobar() {
  const consulta = useViajes({ estado: "pendiente_aprobacion" });
  return (
    <section aria-labelledby="titulo-por-aprobar" className="flex flex-col gap-3">
      <h2 id="titulo-por-aprobar" className="text-xl font-bold">
        Por aprobar
      </h2>
      {consulta.isPending ? (
        <EsqueletoLista texto="Cargando los viajes por aprobar…" filas={2} />
      ) : consulta.error && consulta.viajes.length === 0 ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : consulta.viajes.length === 0 ? (
        <p className="rounded-tarjeta border border-linea bg-superficie p-4 text-texto-secundario">
          No hay viajes esperando aprobación.
        </p>
      ) : (
        <ul aria-label="Viajes por aprobar" className="flex flex-col gap-3">
          {consulta.viajes.map((v) => (
            <TarjetaPorAprobar key={v.id} viaje={v} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function PantallaViajes({ estado }: { estado?: EstadoViaje }) {
  const permiso = usePermiso();
  const esAdmin = permiso === "admin";
  const consulta = useViajes(estado ? { estado } : {});
  const enCurso = permiso === "colaborador" ? consulta.viajes.find((v) => v.en_curso) : undefined;
  // Con el filtro «Por aprobar», administración ya los ve arriba con sus botones.
  const listaVisible = !(esAdmin && estado === "pendiente_aprobacion");

  return (
    <div className="flex flex-col gap-6">
      <EncabezadoPagina
        migas={[{ texto: "Operaciones" }, { texto: permiso === "colaborador" ? "Mis viajes" : "Viajes" }]}
        titulo={permiso === "colaborador" ? "Mis viajes" : "Viajes"}
        descripcion={
          esAdmin
            ? "Todos los viajes. Primero, los que esperan tu aprobación."
            : permiso === "gestor"
              ? "Los tuyos y los de los proyectos que gestionas."
              : "Tus viajes con su presupuesto y lo que llevas gastado."
        }
        accion={
          <>
            <Link href="/gastos/nuevo" className={clasesBoton("secundario")}>
              Cargar recibo
            </Link>
            <Link href="/cotizar" className={clasesBoton("primario")}>
              Cotizar viaje
            </Link>
          </>
        }
      />
      <Filtros activo={estado} />
      {esAdmin && (!estado || estado === "pendiente_aprobacion") ? <PorAprobar /> : null}

      {listaVisible ? (
        <section aria-labelledby="titulo-lista-viajes" className="flex flex-col gap-3">
          <h2 id="titulo-lista-viajes" className={esAdmin && !estado ? "text-xl font-bold" : "sr-only"}>
            Todos los viajes
          </h2>
          {consulta.isPending ? (
            <EsqueletoLista texto="Cargando los viajes…" />
          ) : consulta.error && consulta.viajes.length === 0 ? (
            <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
          ) : consulta.viajes.length === 0 ? (
            estado ? (
              <p className="rounded-tarjeta border border-linea bg-superficie p-4 text-texto-secundario">
                No hay viajes con ese estado.
              </p>
            ) : (
              <EstadoVacio titulo="Aún no tienes viajes" accion={{ href: "/cotizar", texto: "Cotizar mi primer viaje" }}>
                Cotiza tu viaje: comparamos vuelos por su costo total y, cuando administración apruebe el
                presupuesto, podrás cargar tus recibos.
              </EstadoVacio>
            )
          ) : (
            <>
              {enCurso ? <ResumenViajeEnCurso viaje={enCurso} /> : null}
              <ListaViajes viajes={consulta.viajes} conTitular={permiso !== "colaborador"} />
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
      ) : null}
    </div>
  );
}
