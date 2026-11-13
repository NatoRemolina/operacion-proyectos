"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Boton } from "@/shared/ui/boton";
import { CampoTexto } from "@/shared/ui/campo";
import { Alerta } from "@/shared/ui/estado";

export function FormularioEntrar({
  onEntrar,
  enviando,
  error,
  ayuda,
}: {
  onEntrar: (datos: { correo: string; clave: string }) => void;
  enviando: boolean;
  error: string | null;
  ayuda?: ReactNode;
}) {
  // El correo vive aquí y no se borra cuando el ingreso falla.
  const [correo, setCorreo] = useState("");
  const [clave, setClave] = useState("");

  function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    onEntrar({ correo: correo.trim(), clave });
  }

  return (
    <form onSubmit={enviar} className="flex flex-col gap-4" noValidate={false}>
      {error ? (
        <Alerta tono="error" titulo="No pudimos iniciar tu sesión" rol="alert">
          <p>{error}</p>
        </Alerta>
      ) : null}
      <CampoTexto
        id="correo"
        etiqueta="Correo"
        placeholder="nombre@empresa.com"
        type="email"
        name="correo"
        autoComplete="username"
        inputMode="email"
        required
        value={correo}
        onChange={(e) => setCorreo(e.target.value)}
      />
      <CampoTexto
        id="clave"
        etiqueta="Contraseña"
        type="password"
        name="clave"
        autoComplete="current-password"
        required
        value={clave}
        onChange={(e) => setClave(e.target.value)}
      />
      <Boton type="submit" disabled={enviando} className="w-full">
        {enviando ? "Ingresando…" : "Ingresar"}
      </Boton>
      {ayuda}
    </form>
  );
}
