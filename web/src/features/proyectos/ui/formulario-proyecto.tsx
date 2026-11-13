"use client";

import { useId, useState, type FormEvent } from "react";
import type { ErrorDeAplicacion } from "@/shared/domain/errores";
import { Boton } from "@/shared/ui/boton";
import { CampoTexto } from "@/shared/ui/campo";
import { Alerta } from "@/shared/ui/estado";
import { problemasDeProyecto, type CampoProyecto, type DatosProyecto } from "../domain/proyectos";

/**
 * Alta o edición de un proyecto. Revisa lo mismo que el servidor antes de enviar; si el servidor
 * aún encuentra algo, lo muestra junto al campo que lo causó.
 */
export function FormularioProyecto({
  titulo,
  inicial,
  textoEnviar,
  guardando,
  error,
  onEnviar,
  onCancelar,
}: {
  titulo: string;
  inicial: DatosProyecto;
  textoEnviar: string;
  guardando: boolean;
  error: ErrorDeAplicacion | null;
  onEnviar: (datos: DatosProyecto) => void;
  onCancelar: () => void;
}) {
  const id = useId();
  const [datos, setDatos] = useState<DatosProyecto>(inicial);
  const [intentado, setIntentado] = useState(false);
  const problemas = intentado ? problemasDeProyecto(datos) : {};
  const delServidor = error?.tipo === "validacion" ? error.campos : {};
  const errorDe = (campo: CampoProyecto) => problemas[campo] ?? delServidor[campo] ?? null;
  const errorGeneral = error && (error.tipo !== "validacion" || Object.keys(delServidor).length === 0) ? error : null;

  function cambiar(campo: CampoProyecto, valor: string) {
    setDatos((actual) => ({ ...actual, [campo]: valor }));
  }

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    setIntentado(true);
    if (Object.keys(problemasDeProyecto(datos)).length) return;
    onEnviar(datos);
  }

  return (
    <form
      aria-label={titulo}
      noValidate
      onSubmit={enviar}
      className="flex flex-col gap-4 rounded-tarjeta border border-linea bg-superficie p-4 shadow-tarjeta"
    >
      <h2 className="text-lg font-bold">{titulo}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <CampoTexto
          id={`${id}-nombre`}
          etiqueta="Nombre"
          required
          maxLength={120}
          value={datos.nombre}
          error={errorDe("nombre")}
          onChange={(e) => cambiar("nombre", e.target.value)}
        />
        <CampoTexto
          id={`${id}-cliente`}
          etiqueta="Cliente"
          ayuda="Opcional."
          maxLength={120}
          value={datos.cliente}
          error={errorDe("cliente")}
          onChange={(e) => cambiar("cliente", e.target.value)}
        />
        <CampoTexto
          id={`${id}-ciudad`}
          etiqueta="Ciudad"
          ayuda="Opcional."
          maxLength={80}
          value={datos.ciudad}
          error={errorDe("ciudad")}
          onChange={(e) => cambiar("ciudad", e.target.value)}
        />
        <CampoTexto
          id={`${id}-inicio`}
          etiqueta="Inicio"
          type="date"
          required
          value={datos.fecha_inicio}
          error={errorDe("fecha_inicio")}
          onChange={(e) => cambiar("fecha_inicio", e.target.value)}
        />
        <CampoTexto
          id={`${id}-fin`}
          etiqueta="Fin"
          type="date"
          required
          value={datos.fecha_fin}
          error={errorDe("fecha_fin")}
          onChange={(e) => cambiar("fecha_fin", e.target.value)}
        />
        <CampoTexto
          id={`${id}-moneda`}
          etiqueta="Moneda"
          ayuda="Código de tres letras: USD, EUR…"
          required
          maxLength={3}
          autoCapitalize="characters"
          value={datos.moneda}
          error={errorDe("moneda")}
          onChange={(e) => cambiar("moneda", e.target.value)}
        />
      </div>
      {errorGeneral ? (
        <Alerta tono="error" titulo="No se guardó" rol="alert">
          <p>{errorGeneral.message}</p>
        </Alerta>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Boton type="submit" disabled={guardando}>
          {guardando ? "Guardando…" : textoEnviar}
        </Boton>
        <Boton type="button" variante="secundario" onClick={onCancelar} disabled={guardando}>
          Cancelar
        </Boton>
      </div>
    </form>
  );
}
