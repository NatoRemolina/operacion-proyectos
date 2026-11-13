import type { Dinero } from "@/shared/domain/tipos";
import { formatearDinero } from "@/shared/ui/formato";
import { sentidoDiferencia } from "../domain/proyectos";

const TEXTO = { sobrecosto: "sobre lo previsto", por_debajo: "por debajo de lo previsto", igual: "igual a lo previsto" } as const;

/** Real frente a previsto: la cifra sin signo y, escrito, hacia qué lado va. El color solo acompaña. */
export function Diferencia({ valor, compacta = false }: { valor: Dinero; compacta?: boolean }) {
  const sentido = sentidoDiferencia(valor);
  const absoluto = valor === null ? null : valor.replace(/^-/, "");
  const color = sentido === "sobrecosto" ? "text-error" : sentido === "por_debajo" ? "text-exito" : "";
  return (
    <span className={`inline-flex flex-wrap items-baseline justify-end gap-x-1 ${color}`}>
      <span className="font-semibold tabular-nums">
        {sentido === "sobrecosto" ? "+" : sentido === "por_debajo" ? "−" : ""}
        {formatearDinero(absoluto, "USD")}
      </span>
      <span className={compacta ? "text-xs" : "text-sm"}>{TEXTO[sentido]}</span>
    </span>
  );
}
