"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useProyectos } from "@/features/proyectos/application/proyectos";
import type { Permiso } from "@/shared/domain/navegacion";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { CampoSelector, CampoTexto } from "@/shared/ui/campo";
import { DialogoConfirmacion } from "@/shared/ui/dialogo-confirmacion";
import { Alerta } from "@/shared/ui/estado";
import { useAccionCuenta } from "../application/usuarios";
import { CLAVE_CORTA, CLAVE_MINIMA, PERMISOS, type Cargo, type ResultadoUsuario, type Usuario } from "../domain/usuarios";

const BLOQUE = "flex flex-col gap-3 border-t border-linea pt-4";

/** Todo lo que administración cambia de una cuenta. Cada bloque guarda por separado y dice qué pasó. */
export function PanelCuenta({ usuario, cargos, onCerrar }: { usuario: Usuario; cargos: readonly Cargo[]; onCerrar: () => void }) {
  const id = useId();
  const titulo = useRef<HTMLHeadingElement>(null);
  const { avisar } = useAvisos();
  const [rol, setRol] = useState<Permiso>(usuario.rol);
  const [cargo, setCargo] = useState<number | null>(usuario.cargo?.id ?? null);
  const [proyectos, setProyectos] = useState<number[]>(usuario.proyectos.map((p) => p.id));
  const [clave, setClave] = useState("");
  const [claveCorta, setClaveCorta] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const todosLosProyectos = useProyectos();

  const cambiarRol = useAccionCuenta((repo, valor: Permiso) => repo.cambiarRol(usuario.id, valor));
  const cambiarCargo = useAccionCuenta((repo, valor: number | null) => repo.cambiarCargo(usuario.id, valor));
  const asignar = useAccionCuenta((repo, valor: number[]) => repo.asignarProyectos(usuario.id, valor));
  const estado = useAccionCuenta((repo, valor: boolean) => repo.cambiarEstado(usuario.id, valor));
  const restablecer = useAccionCuenta((repo, valor: string) => repo.restablecerClave(usuario.id, valor));
  const acciones = [cambiarRol, cambiarCargo, asignar, estado, restablecer];
  const ultimoError = acciones.find((a) => a.error && a.error.tipo !== "validacion")?.error ?? null;

  useEffect(() => titulo.current?.focus(), [usuario.id]);

  const listo = (r: ResultadoUsuario) => avisar({ tono: "exito", texto: r.mensaje });

  function enviarClave(evento: FormEvent) {
    evento.preventDefault();
    if (clave.length < CLAVE_MINIMA) {
      setClaveCorta(true);
      return;
    }
    setClaveCorta(false);
    restablecer.mutate(clave, {
      onSuccess: (r) => {
        setClave("");
        listo(r);
      },
    });
  }

  const errorClave = claveCorta ? CLAVE_CORTA : restablecer.error?.tipo === "validacion" ? (restablecer.error.campos.clave ?? null) : null;
  const errorCargo = cambiarCargo.error?.tipo === "validacion" ? (cambiarCargo.error.campos.cargo_id ?? null) : null;
  const opcionesCargo = cargos.filter((c) => c.activo || c.id === usuario.cargo?.id);

  return (
    <section
      aria-labelledby={`${id}-titulo`}
      className="flex flex-col gap-4 rounded-tarjeta border border-marca bg-superficie p-4 shadow-tarjeta"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={`${id}-titulo`} ref={titulo} tabIndex={-1} className="text-lg font-bold">
            Cuenta de {usuario.nombre}
          </h2>
          <p className="text-sm text-texto-secundario">
            {usuario.codigo} · {usuario.correo}
          </p>
        </div>
        <Boton variante="secundario" onClick={onCerrar}>
          Cerrar
        </Boton>
      </div>

      {ultimoError ? (
        <Alerta tono="error" titulo="No se hizo el cambio" rol="alert">
          <p>{ultimoError.message}</p>
        </Alerta>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <form
          className={BLOQUE}
          onSubmit={(e) => {
            e.preventDefault();
            cambiarRol.mutate(rol, { onSuccess: listo });
          }}
        >
          <CampoSelector
            id={`${id}-rol`}
            etiqueta="Permiso"
            ayuda="Cambiarlo cierra sus sesiones abiertas: entrará de nuevo con el permiso nuevo."
            value={rol}
            onChange={(e) => setRol(e.target.value as Permiso)}
          >
            {PERMISOS.map((p) => (
              <option key={p.valor} value={p.valor}>
                {p.texto}
              </option>
            ))}
          </CampoSelector>
          <Boton type="submit" variante="secundario" className="self-start" disabled={cambiarRol.isPending || rol === usuario.rol}>
            {cambiarRol.isPending ? "Guardando…" : "Guardar permiso"}
          </Boton>
        </form>

        <form
          className={BLOQUE}
          onSubmit={(e) => {
            e.preventDefault();
            cambiarCargo.mutate(cargo, { onSuccess: listo });
          }}
        >
          <CampoSelector
            id={`${id}-cargo`}
            etiqueta="Cargo"
            ayuda="Qué hace en la empresa. No da permisos."
            value={cargo ?? ""}
            error={errorCargo}
            onChange={(e) => setCargo(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Sin cargo</option>
            {opcionesCargo.map((c) => (
              <option key={c.id} value={c.id}>
                {c.activo ? c.nombre : `${c.nombre} (desactivado)`}
              </option>
            ))}
          </CampoSelector>
          <Boton
            type="submit"
            variante="secundario"
            className="self-start"
            disabled={cambiarCargo.isPending || cargo === (usuario.cargo?.id ?? null)}
          >
            {cambiarCargo.isPending ? "Guardando…" : "Guardar cargo"}
          </Boton>
        </form>

        <form
          className={BLOQUE}
          onSubmit={(e) => {
            e.preventDefault();
            asignar.mutate(proyectos, { onSuccess: listo });
          }}
        >
          <fieldset className="flex flex-col gap-2">
            <legend className="font-semibold">Proyectos que gestiona</legend>
            {usuario.rol !== "gestor" ? (
              <p className="text-sm text-texto-secundario">Solo cuentan con el permiso de gestor de proyecto.</p>
            ) : null}
            {todosLosProyectos.isPending ? (
              <p role="status" className="text-sm text-texto-secundario">
                Cargando los proyectos…
              </p>
            ) : todosLosProyectos.error ? (
              <p className="text-sm text-error">No se pudieron cargar los proyectos.</p>
            ) : (
              todosLosProyectos.proyectos.map((p) => (
                <label key={p.id} className="flex min-h-11 items-center gap-3">
                  <input
                    type="checkbox"
                    className="size-5 accent-marca"
                    checked={proyectos.includes(p.id)}
                    onChange={(e) =>
                      setProyectos((actual) => (e.target.checked ? [...actual, p.id] : actual.filter((x) => x !== p.id)))
                    }
                  />
                  {p.nombre}
                </label>
              ))
            )}
          </fieldset>
          <Boton type="submit" variante="secundario" className="self-start" disabled={asignar.isPending}>
            {asignar.isPending ? "Guardando…" : "Guardar proyectos"}
          </Boton>
        </form>

        <form className={BLOQUE} onSubmit={enviarClave} noValidate>
          <CampoTexto
            id={`${id}-clave`}
            etiqueta="Contraseña nueva"
            type="password"
            autoComplete="new-password"
            ayuda="10 caracteres o más. Cierra sus sesiones abiertas; no se vuelve a mostrar."
            value={clave}
            error={errorClave}
            onChange={(e) => setClave(e.target.value)}
          />
          <Boton type="submit" variante="secundario" className="self-start" disabled={restablecer.isPending}>
            {restablecer.isPending ? "Guardando…" : "Restablecer contraseña"}
          </Boton>
        </form>
      </div>

      <div className={BLOQUE}>
        <p className="font-semibold">Estado: {usuario.activo ? "activa" : "desactivada"}</p>
        {usuario.activo ? (
          <Boton variante="peligro" className="self-start" onClick={() => setConfirmando(true)} disabled={estado.isPending}>
            Desactivar la cuenta
          </Boton>
        ) : (
          <Boton className="self-start" onClick={() => estado.mutate(true, { onSuccess: listo })} disabled={estado.isPending}>
            {estado.isPending ? "Reactivando…" : "Reactivar la cuenta"}
          </Boton>
        )}
      </div>

      <DialogoConfirmacion
        abierto={confirmando}
        titulo={`¿Desactivar la cuenta de ${usuario.nombre}?`}
        efecto="No podrá entrar y se cerrarán sus sesiones abiertas. Su historial se conserva y la puedes reactivar cuando quieras."
        confirmar="Desactivar"
        peligro
        enviando={estado.isPending}
        onCancelar={() => setConfirmando(false)}
        onConfirmar={() =>
          estado.mutate(false, {
            onSuccess: listo,
            onSettled: () => setConfirmando(false),
          })
        }
      />
    </section>
  );
}
