import type { ReactNode } from "react";

/** Tono de un estado. El color siempre acompaña a un texto y a un símbolo, nunca va solo. */
export type Tono = "exito" | "aviso" | "error" | "neutro" | "info";

const ESTILO: Record<Tono, { caja: string; simbolo: string }> = {
  exito: { caja: "border-exito bg-exito-suave text-exito", simbolo: "✓" },
  aviso: { caja: "border-aviso bg-aviso-suave text-aviso", simbolo: "!" },
  error: { caja: "border-error bg-error-suave text-error", simbolo: "✕" },
  neutro: { caja: "border-neutro bg-neutro-suave text-neutro", simbolo: "•" },
  info: { caja: "border-marca bg-marca-suave text-marca", simbolo: "i" },
};

export function InsigniaEstado({ tono, children }: { tono: Tono; children: ReactNode }) {
  const { caja, simbolo } = ESTILO[tono];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-sm font-semibold ${caja}`}
    >
      <span aria-hidden="true">{simbolo}</span>
      {children}
    </span>
  );
}

export function Alerta({
  tono,
  titulo,
  children,
  rol,
}: {
  tono: Tono;
  titulo: ReactNode;
  children?: ReactNode;
  /** `alert` para errores que interrumpen; `status` para avisos; sin rol si ya hay una región viva. */
  rol?: "alert" | "status";
}) {
  const { caja, simbolo } = ESTILO[tono];
  return (
    <div role={rol} className={`rounded-tarjeta border-l-4 p-4 ${caja}`}>
      <p className="flex items-start gap-2 font-bold">
        <span aria-hidden="true">{simbolo}</span>
        <span>{titulo}</span>
      </p>
      {children ? <div className="mt-1 pl-5 text-texto">{children}</div> : null}
    </div>
  );
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <p role="status" className="py-6 text-texto-secundario">
      {texto}
    </p>
  );
}
