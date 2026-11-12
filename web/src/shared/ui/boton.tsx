import type { ButtonHTMLAttributes } from "react";

export type VarianteBoton = "primario" | "secundario" | "texto" | "peligro";

// Respuesta inmediata al presionar: escala 0,97 en 100 ms (solo se anima la transformación).
export const PRESIONAR = "se-mueve transition-transform duration-100 ease-out active:scale-97 disabled:active:scale-100";

const BASE =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg py-2 text-base font-semibold " +
  `no-underline disabled:cursor-not-allowed disabled:opacity-60 ${PRESIONAR}`;

const VARIANTES: Record<VarianteBoton, string> = {
  primario: "px-4 bg-marca text-sobre-marca hover:bg-marca-oscura hover:text-sobre-marca",
  secundario:
    "px-4 border border-borde-campo bg-superficie text-texto hover:bg-neutro-suave hover:text-texto",
  texto: "px-1 text-marca underline underline-offset-3 hover:text-marca-oscura",
  /** Acciones con efecto difícil de deshacer (rechazar, cerrar). */
  peligro: "px-4 bg-error text-sobre-marca hover:bg-error/90 hover:text-sobre-marca",
};

/** Clases de botón para usar también en enlaces que se ven como botón. */
export function clasesBoton(variante: VarianteBoton = "primario", extra = ""): string {
  return `${BASE} ${VARIANTES[variante]} ${extra}`.trim();
}

export function Boton({
  variante = "primario",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: VarianteBoton }) {
  return <button type={type} className={clasesBoton(variante, className)} {...props} />;
}
