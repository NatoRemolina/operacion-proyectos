"use client";

import { useState } from "react";
import { usePermiso } from "@/shared/application/identidad";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { Distintivo } from "@/shared/ui/distintivo";
import { EncabezadoPagina } from "@/shared/ui/encabezado-pagina";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { EsqueletoLista } from "@/shared/ui/esqueleto";
import { Tabla } from "@/shared/ui/tabla";
import { useCargos, useUsuarios } from "../application/usuarios";
import type { Usuario } from "../domain/usuarios";
import { FormularioCuenta } from "./formulario-cuenta";
import { PanelCuenta } from "./panel-cuenta";
import { SeccionCargos } from "./seccion-cargos";

function Telegram({ usuario }: { usuario: Usuario }) {
  if (!usuario.telegram.vinculado) return <span className="text-texto-secundario">Sin vincular</span>;
  return <span>{usuario.telegram.usuario ? `@${usuario.telegram.usuario}` : "Vinculado"}</span>;
}

export function PantallaUsuarios() {
  const esAdmin = usePermiso() === "admin";
  const consulta = useUsuarios();
  const cargos = useCargos();
  const { avisar } = useAvisos();
  const [creando, setCreando] = useState(false);
  const [elegida, setElegida] = useState<number | null>(null);
  const usuarioElegido = consulta.usuarios.find((u) => u.id === elegida) ?? null;

  return (
    <div className="flex flex-col gap-6 md:gap-8">
      <EncabezadoPagina
        migas={[{ texto: "Usuarios" }]}
        titulo="Usuarios y cargos"
        descripcion="Las cuentas de la plataforma: permiso, cargo, proyectos que gestiona y estado. Nadie se quita su propio permiso de administración ni desactiva su cuenta."
        accion={
          esAdmin && !creando && consulta.isSuccess ? <Boton onClick={() => setCreando(true)}>Nueva cuenta</Boton> : null
        }
      />

      {creando ? (
        <FormularioCuenta
          cargos={cargos.data ?? []}
          onCancelar={() => setCreando(false)}
          onCreada={(r) => {
            setCreando(false);
            avisar({ tono: "exito", texto: r.mensaje });
          }}
        />
      ) : null}

      {usuarioElegido ? (
        <PanelCuenta key={usuarioElegido.id} usuario={usuarioElegido} cargos={cargos.data ?? []} onCerrar={() => setElegida(null)} />
      ) : null}

      {consulta.isPending ? (
        <EsqueletoLista texto="Cargando las cuentas…" />
      ) : consulta.error && consulta.usuarios.length === 0 ? (
        <ErrorConsulta error={consulta.error} onReintentar={() => void consulta.refetch()} />
      ) : (
        <>
          <Tabla<Usuario>
            titulo="Cuentas"
            filas={consulta.usuarios}
            claveFila={(u) => u.id}
            columnas={[
              {
                clave: "persona",
                encabezado: "Persona",
                principal: true,
                celda: (u) => (
                  <span className="flex flex-col">
                    <span className="font-semibold">{u.nombre}</span>
                    <span className="text-sm break-all text-texto-secundario">{u.correo}</span>
                  </span>
                ),
              },
              { clave: "codigo", encabezado: "Código", celda: (u) => u.codigo, sinCorte: true },
              { clave: "rol", encabezado: "Permiso", celda: (u) => u.rol_texto },
              { clave: "cargo", encabezado: "Cargo", celda: (u) => u.cargo?.nombre ?? <span className="text-texto-secundario">Sin cargo</span> },
              {
                clave: "proyectos",
                encabezado: "Proyectos",
                celda: (u) =>
                  u.rol === "gestor" && u.proyectos.length ? (
                    <ul className="text-sm">
                      {u.proyectos.map((p) => (
                        <li key={p.id}>{p.nombre}</li>
                      ))}
                    </ul>
                  ) : (
                    <span className="text-texto-secundario">—</span>
                  ),
              },
              {
                clave: "estado",
                encabezado: "Estado",
                celda: (u) => <Distintivo tono={u.activo ? "exito" : "neutro"}>{u.activo ? "Activa" : "Desactivada"}</Distintivo>,
              },
              { clave: "telegram", encabezado: "Telegram", celda: (u) => <Telegram usuario={u} /> },
            ]}
            encabezadoAcciones="Acción"
            acciones={(u) => (
              <Boton
                variante="secundario"
                aria-label={`Gestionar la cuenta de ${u.nombre}`}
                onClick={() => {
                  setCreando(false);
                  setElegida(u.id);
                }}
              >
                Gestionar
              </Boton>
            )}
          />
          {consulta.hasNextPage ? (
            <Boton
              variante="secundario"
              className="self-start"
              onClick={() => void consulta.fetchNextPage()}
              disabled={consulta.isFetchingNextPage}
            >
              {consulta.isFetchingNextPage ? "Cargando…" : "Ver más cuentas"}
            </Boton>
          ) : null}
          <SeccionCargos cargos={cargos.data} error={cargos.error} />
        </>
      )}
    </div>
  );
}
