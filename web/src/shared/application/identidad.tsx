"use client";

import { createContext, useContext, type PropsWithChildren } from "react";

/**
 * Identificador de la persona con sesión. Solo sirve para aislar la caché por persona:
 * el servidor nunca lo acepta como prueba de identidad (la identidad sale de la cookie).
 */
const IdentidadContexto = createContext<number | null>(null);

export function IdentidadProvider({ personaId, children }: PropsWithChildren<{ personaId: number }>) {
  return <IdentidadContexto.Provider value={personaId}>{children}</IdentidadContexto.Provider>;
}

export function usePersonaId(): number {
  const id = useContext(IdentidadContexto);
  if (id === null) throw new Error("Falta IdentidadProvider: la pantalla requiere sesión.");
  return id;
}

/** Raíz de toda clave de caché con datos de la persona; al salir se borra completa. */
export function claveDePersona(personaId: number, ...resto: readonly unknown[]) {
  return ["persona", personaId, ...resto] as const;
}
