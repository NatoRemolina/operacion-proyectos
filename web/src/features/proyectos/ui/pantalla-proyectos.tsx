"use client";

import { useState } from "react";
import { usePermiso } from "@/shared/application/identidad";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { EstadoVacio } from "@/shared/ui/estado-vacio";
import { formatearDinero, formatearRango } from "@/shared/ui/formato";
import { Tabla } from "@/shared/ui/tabla";
import { useCrearProyecto, useProyectos } from "../application/proyectos";
import { datosDeProyecto, type ProyectoResumen } from "../domain/proyectos";
import { Diferencia } from "./diferencia";
import { FormularioProyecto } from "./formulario-proyecto";

function plural(n: number, uno: string, varios: string) {
  return `${n} ${n === 1 ? uno : varios}`;
}

export function PantallaProyectos() {
  const permiso = usePermiso();
  const esAdmin = permiso === "admin";
  const consulta = useProyectos();
  const crear = useCrearProyecto();
  const { avisar } = useAvisos();
  const [creando, setCreando] = useState(false);

  function abrir() {
    crear.reset();
    setCreando(true);
  }

  return (
    <div className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Proyectos" }]}
        titulo="Proyectos"
        descripcion={
          esAdmin
            ? "Cada cotización, viaje y gasto pertenece a un proyecto. Aquí ves lo previsto frente a lo gastado en cada uno."
            : "Los proyectos que gestionas, con lo previsto frente a lo gastado."
        }
        accion={
          esAdmin && !creando ? (
            <Boton onClick={abrir} aria-expanded={false}>
              Nuevo proyecto
            </Boton>
          ) : null
        }
      />

      {creando ? (
        <FormularioProyecto
          titulo="Nuevo proyecto"
          inicial={datosDeProyecto()}
          textoEnviar="Crear proyecto"
          guardando={crear.isPending}
          error={crear.error}
          onCancelar={() => setCreando(false)}
          onEnviar={(datos) =>
            crear.mutate(datos, {
              onSuccess: (p) => {
                setCreando(false);
                avisar({ tono: "exito", texto: `Proyecto «${p.nombre}» creado.` });
              },
            })
          }
        />
      ) : null}

      {consulta.isPending ? (
        <EsqueletoLista texto="Cargando los proyectos…" />
      ) : consulta.error && consulta.proyectos.length === 0 ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : consulta.proyectos.length === 0 ? (
        <EstadoVacio titulo="Aún no hay proyectos">
          {esAdmin ? "Crea el primero con «Nuevo proyecto»." : "Todavía no tienes proyectos asignados para gestionar."}
        </EstadoVacio>
      ) : (
        <>
          <Tabla<ProyectoResumen>
            titulo="Proyectos"
            filas={consulta.proyectos}
            claveFila={(p) => p.id}
            hrefFila={(p) => `/proyectos/${p.id}`}
            columnas={[
              { clave: "nombre", encabezado: "Proyecto", celda: (p) => p.nombre, principal: true },
              {
                clave: "lugar",
                encabezado: "Ciudad y fechas",
                celda: (p) => (
                  <span className="text-sm">
                    {p.ciudad ?? "Sin ciudad"}
                    <br />
                    <span className="text-texto-secundario">{formatearRango(p.fecha_inicio, p.fecha_fin)}</span>
                  </span>
                ),
              },
              {
                clave: "actividad",
                encabezado: "Actividad",
                celda: (p) => (
                  <span className="text-sm">
                    {plural(p.viajes, "viaje", "viajes")} · {plural(p.gastos, "gasto", "gastos")}
                  </span>
                ),
              },
              { clave: "previsto", encabezado: "Previsto", celda: (p) => formatearDinero(p.previsto_usd, "USD"), alinear: "fin" },
              { clave: "real", encabezado: "Real aprobado", celda: (p) => formatearDinero(p.real_usd, "USD"), alinear: "fin" },
              { clave: "diferencia", encabezado: "Diferencia", celda: (p) => <Diferencia valor={p.diferencia_usd} compacta />, alinear: "fin" },
            ]}
          />
          {consulta.hasNextPage ? (
            <Boton
              variante="secundario"
              className="self-start"
              onClick={() => void consulta.fetchNextPage()}
              disabled={consulta.isFetchingNextPage}
            >
              {consulta.isFetchingNextPage ? "Cargando…" : "Ver más proyectos"}
            </Boton>
          ) : null}
        </>
      )}
    </div>
  );
}
