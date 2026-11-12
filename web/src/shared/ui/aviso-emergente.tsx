"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import type { Tono } from "./estado";

export interface Aviso {
  tono: Extract<Tono, "exito" | "aviso" | "error" | "info">;
  texto: string;
}

const DURACION_MS = 6000;

const SIMBOLO: Record<Aviso["tono"], string> = { exito: "✓", aviso: "!", error: "✕", info: "i" };
const BORDE: Record<Aviso["tono"], string> = {
  exito: "border-exito",
  aviso: "border-aviso",
  error: "border-error",
  info: "border-marca",
};
const COLOR: Record<Aviso["tono"], string> = {
  exito: "text-exito",
  aviso: "text-aviso",
  error: "text-error",
  info: "text-marca",
};

// Sin proveedor (por ejemplo, en una prueba aislada) avisar no hace nada.
const AvisosContexto = createContext<(aviso: Aviso) => void>(() => {});

/** Avisos emergentes tras una acción: se anuncian en una región viva y se cierran solos. */
export function AvisosProvider({ children }: { children: ReactNode }) {
  const [avisos, setAvisos] = useState<(Aviso & { id: number })[]>([]);
  const siguiente = useRef(1);

  const cerrar = useCallback((id: number) => setAvisos((actuales) => actuales.filter((a) => a.id !== id)), []);
  const avisar = useCallback(
    (aviso: Aviso) => {
      const id = siguiente.current++;
      setAvisos((actuales) => [...actuales.slice(-2), { ...aviso, id }]);
      setTimeout(() => cerrar(id), DURACION_MS);
    },
    [cerrar],
  );

  return (
    <AvisosContexto.Provider value={avisar}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-20 z-50 flex flex-col items-stretch gap-2 md:inset-x-auto md:bottom-6 md:right-6 md:w-96"
      >
        {avisos.map((a) => (
          <div
            key={a.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-tarjeta border-l-4 bg-superficie p-4 shadow-lg ${BORDE[a.tono]}`}
          >
            <span aria-hidden="true" className={`font-bold ${COLOR[a.tono]}`}>
              {SIMBOLO[a.tono]}
            </span>
            <p className="flex-1 font-semibold">{a.texto}</p>
            <button
              type="button"
              aria-label="Cerrar aviso"
              onClick={() => cerrar(a.id)}
              className="-m-2 inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-texto-secundario hover:bg-neutro-suave"
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>
        ))}
      </div>
    </AvisosContexto.Provider>
  );
}

export function useAvisos() {
  const avisar = useContext(AvisosContexto);
  return useMemo(() => ({ avisar }), [avisar]);
}
