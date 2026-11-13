"use client";

import { useId, useState, type FormEvent } from "react";
import type { Permiso } from "@/shared/domain/navegacion";
import { Boton } from "@/shared/ui/boton";
import { CampoSelector, CampoTexto } from "@/shared/ui/campo";
import { Alerta } from "@/shared/ui/estado";
import { useAccionCuenta } from "../application/usuarios";
import { PERMISOS, problemasDeCuenta, type Cargo, type CampoCuenta, type NuevaCuenta, type ResultadoUsuario } from "../domain/usuarios";

const VACIA: NuevaCuenta = { correo: "", nombre: "", rol: "colaborador", clave: "", cargo_id: null };

/** Alta de una cuenta. La contraseña inicial la escribe administración y se le entrega a la persona por un canal seguro. */
export function FormularioCuenta({
  cargos,
  onCreada,
  onCancelar,
}: {
  cargos: readonly Cargo[];
  onCreada: (resultado: ResultadoUsuario) => void;
  onCancelar: () => void;
}) {
  const id = useId();
  const crear = useAccionCuenta((repo, datos: NuevaCuenta) => repo.crear(datos));
  const [datos, setDatos] = useState<NuevaCuenta>(VACIA);
  const [intentado, setIntentado] = useState(false);
  const problemas = intentado ? problemasDeCuenta(datos) : {};
  const delServidor = crear.error?.tipo === "validacion" ? crear.error.campos : {};
  const errorDe = (campo: CampoCuenta) => problemas[campo] ?? delServidor[campo] ?? null;
  const errorGeneral = crear.error && Object.keys(delServidor).length === 0 ? crear.error : null;

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    setIntentado(true);
    if (Object.keys(problemasDeCuenta(datos)).length) return;
    crear.mutate(datos, {
      onSuccess: (resultado) => {
        setDatos(VACIA);
        onCreada(resultado);
      },
    });
  }

  return (
    <form
      aria-label="Nueva cuenta"
      noValidate
      onSubmit={enviar}
      className="flex flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta"
    >
      <h2 className="text-lg font-bold">Nueva cuenta</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <CampoTexto
          id={`${id}-correo`}
          etiqueta="Correo"
          type="email"
          autoComplete="off"
          required
          value={datos.correo}
          error={errorDe("correo")}
          onChange={(e) => setDatos((d) => ({ ...d, correo: e.target.value }))}
        />
        <CampoTexto
          id={`${id}-nombre`}
          etiqueta="Nombre"
          required
          maxLength={80}
          value={datos.nombre}
          error={errorDe("nombre")}
          onChange={(e) => setDatos((d) => ({ ...d, nombre: e.target.value }))}
        />
        <CampoSelector
          id={`${id}-rol`}
          etiqueta="Permiso"
          ayuda="Qué puede hacer en la plataforma."
          value={datos.rol}
          error={errorDe("rol")}
          onChange={(e) => setDatos((d) => ({ ...d, rol: e.target.value as Permiso }))}
        >
          {PERMISOS.map((p) => (
            <option key={p.valor} value={p.valor}>
              {p.texto}
            </option>
          ))}
        </CampoSelector>
        <CampoSelector
          id={`${id}-cargo`}
          etiqueta="Cargo"
          ayuda="Qué hace en la empresa. No da permisos."
          value={datos.cargo_id ?? ""}
          error={errorDe("cargo_id")}
          onChange={(e) => setDatos((d) => ({ ...d, cargo_id: e.target.value ? Number(e.target.value) : null }))}
        >
          <option value="">Sin cargo</option>
          {cargos
            .filter((c) => c.activo)
            .map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre}
              </option>
            ))}
        </CampoSelector>
        <CampoTexto
          id={`${id}-clave`}
          etiqueta="Contraseña inicial"
          type="password"
          autoComplete="new-password"
          ayuda="10 caracteres o más. Entrégasela a la persona por un canal seguro: no se vuelve a mostrar."
          required
          value={datos.clave}
          error={errorDe("clave")}
          onChange={(e) => setDatos((d) => ({ ...d, clave: e.target.value }))}
        />
      </div>
      {errorGeneral ? (
        <Alerta tono="error" titulo="No se creó la cuenta" rol="alert">
          <p>{errorGeneral.message}</p>
        </Alerta>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Boton type="submit" disabled={crear.isPending}>
          {crear.isPending ? "Creando…" : "Crear cuenta"}
        </Boton>
        <Boton type="button" variante="secundario" onClick={onCancelar} disabled={crear.isPending}>
          Cancelar
        </Boton>
      </div>
    </form>
  );
}
