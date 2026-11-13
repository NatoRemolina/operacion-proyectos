"use client";

import { useState, type FormEvent } from "react";
import { useAvisos } from "@/shared/ui/aviso-emergente";
import { Boton } from "@/shared/ui/boton";
import { CampoTexto } from "@/shared/ui/campo";
import { Distintivo } from "@/shared/ui/distintivo";
import { Alerta } from "@/shared/ui/estado";
import { useAccionCargo } from "../application/usuarios";
import { problemaDeCargo, type Cargo } from "../domain/usuarios";

function FilaCargo({ cargo }: { cargo: Cargo }) {
  const { avisar } = useAvisos();
  const [nombre, setNombre] = useState(cargo.nombre);
  const cambiar = useAccionCargo((repo, cambio: { nombre?: string; activo?: boolean }) => repo.cambiarCargoCatalogo(cargo.id, cambio));
  const error = cambiar.error?.tipo === "validacion" ? (cambiar.error.campos.nombre ?? cambiar.error.message) : cambiar.error?.message;

  return (
    <li className="flex flex-col gap-2 border-b border-linea py-3 last:border-b-0">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          cambiar.mutate({ nombre }, { onSuccess: () => avisar({ tono: "exito", texto: "Cargo renombrado." }) });
        }}
      >
        <div className="min-w-0 flex-1 basis-48">
          <label htmlFor={`cargo-${cargo.id}`} className="sr-only">
            Nombre del cargo {cargo.nombre}
          </label>
          <input
            id={`cargo-${cargo.id}`}
            maxLength={60}
            value={nombre}
            aria-invalid={error ? true : undefined}
            onChange={(e) => setNombre(e.target.value)}
            className="block min-h-11 w-full rounded-lg border border-borde-campo bg-superficie px-3 py-2 text-base aria-invalid:border-2 aria-invalid:border-error"
          />
        </div>
        <Boton
          type="submit"
          variante="secundario"
          aria-label={`Guardar el nombre de ${cargo.nombre}`}
          disabled={cambiar.isPending || nombre.trim() === cargo.nombre}
        >
          Guardar
        </Boton>
        <Boton
          variante="texto"
          aria-label={`${cargo.activo ? "Desactivar" : "Reactivar"} el cargo ${cargo.nombre}`}
          disabled={cambiar.isPending}
          onClick={() =>
            cambiar.mutate(
              { activo: !cargo.activo },
              { onSuccess: () => avisar({ tono: "exito", texto: `Cargo «${cargo.nombre}» ${cargo.activo ? "desactivado" : "reactivado"}.` }) },
            )
          }
        >
          {cargo.activo ? "Desactivar" : "Reactivar"}
        </Boton>
      </form>
      <p className="flex flex-wrap items-center gap-2 text-sm text-texto-secundario">
        <Distintivo tono={cargo.activo ? "exito" : "neutro"}>{cargo.activo ? "Activo" : "Desactivado"}</Distintivo>
        {cargo.personas === 1 ? "1 persona" : `${cargo.personas} personas`}
        {!cargo.activo && cargo.personas ? " lo conservan; no se ofrece en cuentas nuevas." : null}
      </p>
      {error ? (
        <p className="text-sm font-semibold text-error">
          <span aria-hidden="true">✕ </span>
          {error}
        </p>
      ) : null}
    </li>
  );
}

/** El catálogo de cargos: qué hace cada persona en la empresa. Un cargo nunca se borra; se desactiva. */
export function SeccionCargos({ cargos, error }: { cargos: readonly Cargo[] | undefined; error: Error | null }) {
  const { avisar } = useAvisos();
  const [nuevo, setNuevo] = useState("");
  const [intentado, setIntentado] = useState(false);
  const crear = useAccionCargo((repo, nombre: string) => repo.crearCargo(nombre));
  const problema = intentado ? problemaDeCargo(nuevo.trim()) : null;
  const errorNuevo = problema ?? (crear.error?.tipo === "validacion" ? (crear.error.campos.nombre ?? null) : (crear.error?.message ?? null));

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    setIntentado(true);
    if (problemaDeCargo(nuevo.trim())) return;
    crear.mutate(nuevo, {
      onSuccess: (c) => {
        setNuevo("");
        setIntentado(false);
        avisar({ tono: "exito", texto: `Cargo «${c.nombre}» creado.` });
      },
    });
  }

  return (
    <section aria-labelledby="titulo-cargos" className="flex flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta">
      <div>
        <h2 id="titulo-cargos" className="text-xl font-bold">
          Cargos
        </h2>
        <p className="max-w-prose text-sm text-texto-secundario">
          Qué hace cada persona en la empresa (pilotaje de dron, edición de video…). No da permisos. Un cargo con personas no se
          borra: se desactiva y quien lo tiene lo conserva.
        </p>
      </div>
      <form className="flex flex-wrap items-end gap-2" onSubmit={enviar} noValidate>
        <div className="min-w-0 flex-1 basis-56">
          <CampoTexto
            id="cargo-nuevo"
            etiqueta="Nuevo cargo"
            maxLength={60}
            value={nuevo}
            error={errorNuevo}
            onChange={(e) => setNuevo(e.target.value)}
          />
        </div>
        <Boton type="submit" disabled={crear.isPending} className="mb-auto mt-7">
          {crear.isPending ? "Agregando…" : "Agregar cargo"}
        </Boton>
      </form>
      {error ? (
        <Alerta tono="error" titulo="No se pudieron cargar los cargos" rol="alert">
          <p>{error.message}</p>
        </Alerta>
      ) : !cargos ? (
        <p role="status" className="text-texto-secundario">
          Cargando los cargos…
        </p>
      ) : (
        <ul aria-label="Cargos de la empresa" className="flex flex-col">
          {cargos.map((c) => (
            <FilaCargo key={`${c.id}-${c.nombre}-${c.activo}`} cargo={c} />
          ))}
        </ul>
      )}
    </section>
  );
}
