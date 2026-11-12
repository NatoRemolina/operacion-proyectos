"use client";

import { createContext, useContext, type PropsWithChildren, type ReactElement } from "react";

/**
 * Crea un par Provider/hook tipado para inyectar un puerto. El Context es solo el mecanismo
 * de inyección: la abstracción es la interfaz del dominio y la elección vive en `composition`.
 */
export function crearContextoRepositorio<T>(nombre: string) {
  const Contexto = createContext<T | null>(null);
  Contexto.displayName = nombre;

  function Proveedor({
    repositorio,
    children,
  }: PropsWithChildren<{ repositorio: T }>): ReactElement {
    return <Contexto.Provider value={repositorio}>{children}</Contexto.Provider>;
  }

  function useRepositorio(): T {
    const repositorio = useContext(Contexto);
    if (repositorio === null) throw new Error(`Falta el proveedor de ${nombre}.`);
    return repositorio;
  }

  return { Proveedor, useRepositorio };
}
