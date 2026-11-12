import Link from "next/link";
import type { ReactNode } from "react";

export interface EnlaceMenu {
  href: string;
  texto: string;
  /** Texto corto para la barra inferior del celular. */
  corto: string;
}

export function Marca({ tamano = "grande" }: { tamano?: "grande" | "pequena" }) {
  return (
    <p className="leading-none">
      <span className={`block font-extrabold tracking-wide ${tamano === "grande" ? "text-2xl" : "text-lg"}`}>
        INFLIGHT
      </span>
      <span className="mt-2 block text-[0.7rem] font-semibold tracking-[0.3em] text-sobre-grafito-suave">
        SOLUTIONS
      </span>
    </p>
  );
}

function esActivo(href: string, ruta: string): boolean {
  if (href === "/gastos") return ruta === "/gastos" || /^\/gastos\/\d+/.test(ruta);
  return ruta === href || ruta.startsWith(`${href}/`);
}

const BOTON_OSCURO =
  "inline-flex min-h-11 items-center justify-center rounded-lg border border-sobre-grafito-suave px-4 " +
  "font-semibold text-sobre-grafito hover:bg-white/10 disabled:opacity-60";

/**
 * Marco de las pantallas con sesión: navegación lateral grafito en escritorio y barra
 * inferior en celular (dirección visual del diseño en Figma).
 */
export function MarcoPrivado({
  nombre,
  enlaces,
  rutaActual,
  onSalir,
  saliendo,
  children,
}: {
  nombre: string;
  enlaces: readonly EnlaceMenu[];
  rutaActual: string;
  onSalir: () => void;
  saliendo: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-1">
      <a
        href="#contenido"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-30 focus:rounded-lg focus:bg-superficie focus:p-3"
      >
        Saltar al contenido
      </a>

      <aside className="zona-oscura sticky top-0 hidden h-dvh w-60 shrink-0 flex-col bg-grafito px-5 py-7 text-sobre-grafito md:flex">
        <Marca />
        <nav aria-label="Principal" className="mt-10">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-cian-claro">Operaciones</p>
          <ul className="flex flex-col gap-1">
            {enlaces.map((enlace) => {
              const activo = esActivo(enlace.href, rutaActual);
              return (
                <li key={enlace.href}>
                  <Link
                    href={enlace.href}
                    aria-current={activo ? "page" : undefined}
                    className={`flex min-h-11 items-center rounded-lg px-3 font-semibold no-underline ${
                      activo ? "bg-marca text-sobre-marca" : "hover:bg-white/10"
                    }`}
                  >
                    {enlace.texto}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="mt-auto flex flex-col gap-3">
          <p className="text-sm text-sobre-grafito-suave">
            <span className="sr-only">Sesión de </span>
            {nombre}
          </p>
          <button type="button" className={BOTON_OSCURO} onClick={onSalir} disabled={saliendo}>
            {saliendo ? "Saliendo…" : "Salir"}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="zona-oscura flex items-center justify-between gap-3 bg-grafito px-4 py-3 text-sobre-grafito md:hidden">
          <Marca tamano="pequena" />
          <button type="button" className={BOTON_OSCURO} onClick={onSalir} disabled={saliendo}>
            {saliendo ? "Saliendo…" : "Salir"}
          </button>
        </header>
        <main id="contenido" className="mx-auto w-full max-w-contenido flex-1 px-4 pb-28 pt-6 md:px-8 md:pb-10">
          {children}
        </main>
      </div>

      <nav
        aria-label="Principal"
        className="fixed inset-x-0 bottom-0 z-20 border-t border-linea bg-superficie pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <ul className="grid grid-cols-3">
          {enlaces.map((enlace) => {
            const activo = esActivo(enlace.href, rutaActual);
            return (
              <li key={enlace.href}>
                <Link
                  href={enlace.href}
                  aria-current={activo ? "page" : undefined}
                  className={`flex min-h-14 items-center justify-center border-t-4 px-1 text-center text-sm font-bold uppercase tracking-wide no-underline ${
                    activo ? "border-marca text-marca" : "border-transparent text-texto"
                  }`}
                >
                  {enlace.corto}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

export function AvisoDemo() {
  return (
    <div role="note" className="border-b-2 border-aviso bg-aviso-suave px-4 py-2 text-center text-sm">
      <strong className="text-aviso">
        <span aria-hidden="true">! </span>Datos de demostración
      </strong>{" "}
      <span className="text-texto">Nada de lo que ves aquí es real ni se guarda en la plataforma.</span>
    </div>
  );
}
