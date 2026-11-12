"use client";

import { createContext, useContext, type PropsWithChildren } from "react";
import type { Permiso } from "@/shared/domain/navegacion";

/**
 * Identificador y permiso de la persona con sesión. El identificador aísla la caché por persona;
 * el permiso decide qué botones se muestran. Ninguno es prueba de identidad: el servidor la saca
 * de la cookie y vuelve a comprobar el permiso en cada petición.
 */
const IdentidadContexto = createContext<{ personaId: number; permiso: Permiso } | null>(null);

export function IdentidadProvider({
  personaId,
  permiso = "colaborador",
  children,
}: PropsWithChildren<{ personaId: number; permiso?: Permiso }>) {
  return <IdentidadContexto.Provider value={{ personaId, permiso }}>{children}</IdentidadContexto.Provider>;
}

function useIdentidad() {
  const identidad = useContext(IdentidadContexto);
  if (identidad === null) throw new Error("Falta IdentidadProvider: la pantalla requiere sesión.");
  return identidad;
}

export function usePersonaId(): number {
  return useIdentidad().personaId;
}

/** El permiso de la sesión, solo para decidir qué se muestra. */
export function usePermiso(): Permiso {
  return useIdentidad().permiso;
}

/** Raíz de toda clave de caché con datos de la persona; al salir se borra completa. */
export function claveDePersona(personaId: number, ...resto: readonly unknown[]) {
  return ["persona", personaId, ...resto] as const;
}
