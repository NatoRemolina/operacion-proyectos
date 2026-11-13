import type { SVGProps } from "react";

/** Íconos del asistente. Decorativos: el texto o la etiqueta del botón dicen qué hacen. */
function Icono({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

export function IconoChispa(props: SVGProps<SVGSVGElement>) {
  return (
    <Icono {...props} fill="currentColor" stroke="none">
      <path d="M11 2.5c.3 0 .55.2.62.5l.9 3.6a5 5 0 0 0 3.63 3.63l3.6.9a.64.64 0 0 1 0 1.24l-3.6.9a5 5 0 0 0-3.63 3.63l-.9 3.6a.64.64 0 0 1-1.24 0l-.9-3.6a5 5 0 0 0-3.63-3.63l-3.6-.9a.64.64 0 0 1 0-1.24l3.6-.9A5 5 0 0 0 9.48 6.6l.9-3.6c.07-.3.33-.5.62-.5Z" />
      <path d="M18.5 2c.2 0 .36.13.4.32l.3 1.18c.15.6.62 1.07 1.22 1.22l1.18.3a.41.41 0 0 1 0 .8l-1.18.3c-.6.15-1.07.62-1.22 1.22l-.3 1.18a.41.41 0 0 1-.8 0l-.3-1.18a1.7 1.7 0 0 0-1.22-1.22l-1.18-.3a.41.41 0 0 1 0-.8l1.18-.3c.6-.15 1.07-.62 1.22-1.22l.3-1.18c.04-.19.2-.32.4-.32Z" />
    </Icono>
  );
}

export function IconoCerrar(props: SVGProps<SVGSVGElement>) {
  return (
    <Icono {...props}>
      <path d="M6 6l12 12M18 6 6 18" />
    </Icono>
  );
}

export function IconoEnviar(props: SVGProps<SVGSVGElement>) {
  return (
    <Icono {...props} strokeWidth={2}>
      <path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" />
    </Icono>
  );
}

export function IconoMicrofono(props: SVGProps<SVGSVGElement>) {
  return (
    <Icono {...props}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" />
    </Icono>
  );
}

export function IconoDetener(props: SVGProps<SVGSVGElement>) {
  return (
    <Icono {...props} fill="currentColor" stroke="none">
      <rect x="6.5" y="6.5" width="11" height="11" rx="2.5" />
    </Icono>
  );
}

export function IconoNueva(props: SVGProps<SVGSVGElement>) {
  return (
    <Icono {...props}>
      <path d="M12 20h8M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z" />
    </Icono>
  );
}
