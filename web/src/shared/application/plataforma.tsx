"use client";

import { createContext, useContext, type PropsWithChildren } from "react";

/**
 * Origen de las pantallas actuales de la plataforma (Jinja), para enlazar lo que esta web aún no
 * hace (corregir un gasto, aprobar con excepción, proyectos, usuarios). "" = no configurado.
 */
const PlataformaContexto = createContext("");

export function PlataformaProvider({ origen, children }: PropsWithChildren<{ origen: string }>) {
  return <PlataformaContexto.Provider value={origen}>{children}</PlataformaContexto.Provider>;
}

export function usePlataforma(): string {
  return useContext(PlataformaContexto);
}
