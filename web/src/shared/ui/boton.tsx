import type { ButtonHTMLAttributes } from "react";

export type VarianteBoton = "primario" | "secundario" | "texto";

const BASE =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg py-2 text-base font-semibold " +
  "no-underline transition-colors disabled:cursor-not-allowed disabled:opacity-60";

const VARIANTES: Record<VarianteBoton, string> = {
  primario: "px-4 bg-marca text-sobre-marca hover:bg-marca-oscura hover:text-sobre-marca",
  secundario:
    "px-4 border border-borde-campo bg-superficie text-texto hover:bg-neutro-suave hover:text-texto",
  texto: "px-1 text-marca underline underline-offset-3 hover:text-marca-oscura",
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
