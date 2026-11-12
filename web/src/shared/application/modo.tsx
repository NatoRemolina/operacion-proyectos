"use client";

import { createContext, useContext, type PropsWithChildren } from "react";

/** Información del modo demostración que la interfaz puede mostrar; `null` con datos reales. */
export interface ModoDemo {
  readonly cuentas: readonly { readonly correo: string; readonly clave: string; readonly descripcion: string }[];
}

const ModoContexto = createContext<ModoDemo | null>(null);

export function ModoProvider({ demo, children }: PropsWithChildren<{ demo: ModoDemo | null }>) {
  return <ModoContexto.Provider value={demo}>{children}</ModoContexto.Provider>;
}

export function useModoDemo(): ModoDemo | null {
  return useContext(ModoContexto);
}
