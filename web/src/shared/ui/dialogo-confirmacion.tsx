"use client";

import { useId, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { Boton } from "./boton";

const ENFOCABLES = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Confirmación de una acción con efecto difícil de deshacer (rechazar, cerrar). Explica el
 * efecto, retiene el foco dentro, Escape cancela y al cerrar el foco vuelve a donde estaba.
 */
export function DialogoConfirmacion({
  abierto,
  titulo,
  efecto,
  confirmar,
  cancelar = "Cancelar",
  peligro = false,
  enviando,
  onConfirmar,
  onCancelar,
  children,
}: {
  abierto: boolean;
  titulo: string;
  /** Qué pasará al confirmar, en lenguaje claro. */
  efecto: ReactNode;
  confirmar: string;
  cancelar?: string;
  peligro?: boolean;
  enviando: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
  /** Campos propios (por ejemplo, el motivo). */
  children?: ReactNode;
}) {
  const id = useId();
  const panel = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!abierto) return;
    const previo = document.activeElement as HTMLElement | null;
    // El diálogo nace del botón que lo abrió: su origen de escala es ese botón.
    if (previo && panel.current && previo !== document.body) {
      const desde = previo.getBoundingClientRect();
      const caja = panel.current.getBoundingClientRect();
      panel.current.style.transformOrigin = `${desde.left + desde.width / 2 - caja.left}px ${desde.top + desde.height / 2 - caja.top}px`;
    }
    const primero =
      panel.current?.querySelector<HTMLElement>("input, textarea, select") ??
      panel.current?.querySelector<HTMLElement>(ENFOCABLES);
    primero?.focus();
    return () => previo?.focus();
  }, [abierto]);

  if (!abierto) return null;

  function alTeclear(evento: KeyboardEvent<HTMLDivElement>) {
    if (evento.key === "Escape") {
      evento.stopPropagation();
      if (!enviando) onCancelar();
      return;
    }
    if (evento.key !== "Tab" || !panel.current) return;
    const enfocables = Array.from(panel.current.querySelectorAll<HTMLElement>(ENFOCABLES));
    if (!enfocables.length) return;
    const primero = enfocables[0]!;
    const ultimo = enfocables[enfocables.length - 1]!;
    if (evento.shiftKey && document.activeElement === primero) {
      evento.preventDefault();
      ultimo.focus();
    } else if (!evento.shiftKey && document.activeElement === ultimo) {
      evento.preventDefault();
      primero.focus();
    }
  }

  function enviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!enviando) onConfirmar();
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-velo p-4 transition-opacity duration-200 ease-salida starting:opacity-0 sm:items-center">
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-titulo`}
        aria-describedby={`${id}-efecto`}
        onKeyDown={alTeclear}
        className="se-mueve w-full max-w-md rounded-tarjeta bg-superficie p-5 shadow-lg transition-[scale,opacity] duration-200 ease-salida starting:scale-95 starting:opacity-0 contrast-more:border-2 contrast-more:border-texto"
      >
        <form onSubmit={enviar} className="flex flex-col gap-4">
          <h2 id={`${id}-titulo`} className="text-xl font-bold">
            {titulo}
          </h2>
          <p id={`${id}-efecto`} className="text-texto-secundario">
            {efecto}
          </p>
          {children}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Boton variante="secundario" onClick={onCancelar} disabled={enviando}>
              {cancelar}
            </Boton>
            <Boton type="submit" variante={peligro ? "peligro" : "primario"} disabled={enviando}>
              {enviando ? "Enviando…" : confirmar}
            </Boton>
          </div>
        </form>
      </div>
    </div>
  );
}
