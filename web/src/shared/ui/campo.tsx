import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

const CONTROL =
  "block min-h-11 w-full rounded-lg border border-borde-campo bg-superficie px-3 py-2 text-base text-texto " +
  "placeholder:text-texto-secundario aria-invalid:border-error aria-invalid:border-2";

interface PropsComunes {
  id: string;
  etiqueta: string;
  ayuda?: ReactNode;
  error?: string | null;
}

function describedBy(id: string, ayuda?: ReactNode, error?: string | null) {
  const ids = [ayuda ? `${id}-ayuda` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

function Pie({ id, ayuda, error }: Omit<PropsComunes, "etiqueta">) {
  return (
    <>
      {ayuda ? (
        <p id={`${id}-ayuda`} className="text-sm text-texto-secundario">
          {ayuda}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-sm font-semibold text-error">
          <span aria-hidden="true">✕ </span>
          {error}
        </p>
      ) : null}
    </>
  );
}

export function CampoTexto({
  id,
  etiqueta,
  ayuda,
  error,
  ...input
}: PropsComunes & Omit<InputHTMLAttributes<HTMLInputElement>, "id">) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">
        {etiqueta}
      </label>
      <input
        id={id}
        className={CONTROL}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, ayuda, error)}
        {...input}
      />
      <Pie id={id} ayuda={ayuda} error={error} />
    </div>
  );
}

export function CampoSelector({
  id,
  etiqueta,
  ayuda,
  error,
  children,
  ...select
}: PropsComunes & Omit<SelectHTMLAttributes<HTMLSelectElement>, "id">) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">
        {etiqueta}
      </label>
      <select
        id={id}
        className={CONTROL}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, ayuda, error)}
        {...select}
      >
        {children}
      </select>
      <Pie id={id} ayuda={ayuda} error={error} />
    </div>
  );
}

export function CampoAreaTexto({
  id,
  etiqueta,
  ayuda,
  error,
  ...area
}: PropsComunes & Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "id">) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-semibold">
        {etiqueta}
      </label>
      <textarea
        id={id}
        rows={3}
        className={`${CONTROL} resize-y`}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, ayuda, error)}
        {...area}
      />
      <Pie id={id} ayuda={ayuda} error={error} />
    </div>
  );
}
