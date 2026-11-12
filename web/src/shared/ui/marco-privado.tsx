"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { TEXTO_PERMISO, type EntradaMenu, type Permiso } from "@/shared/domain/navegacion";
import { AvisosProvider } from "./aviso-emergente";
import { PRESIONAR } from "./boton";

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

function esActivo(enlace: EntradaMenu, ruta: string): boolean {
  if (enlace.externa) return false;
  return ruta === enlace.href || ruta.startsWith(`${enlace.href}/`);
}

const BOTON_OSCURO =
  "inline-flex min-h-11 items-center justify-center rounded-lg border border-sobre-grafito-suave px-4 " +
  `font-semibold text-sobre-grafito hover:bg-white/10 disabled:opacity-60 ${PRESIONAR}`;

/** Enlace del menú: las pantallas de esta web navegan sin recargar; las actuales, con un enlace normal. */
function EnlaceMenuOscuro({ enlace, activo, onNavegar }: { enlace: EntradaMenu; activo: boolean; onNavegar?: () => void }) {
  const clases = `flex min-h-11 items-center rounded-lg px-3 font-semibold no-underline ${PRESIONAR} ${
    activo ? "bg-marca text-sobre-marca" : "hover:bg-white/10"
  }`;
  if (enlace.externa) {
    return (
      <a href={enlace.href} className={clases} onClick={onNavegar}>
        {enlace.texto}
      </a>
    );
  }
  return (
    <Link href={enlace.href} aria-current={activo ? "page" : undefined} className={clases} onClick={onNavegar}>
      {enlace.texto}
    </Link>
  );
}

function ListaMenu({
  enlaces,
  rutaActual,
  onNavegar,
}: {
  enlaces: readonly EntradaMenu[];
  rutaActual: string;
  onNavegar?: () => void;
}) {
  return (
    <>
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-cian-claro">Operaciones</p>
      <ul className="flex flex-col gap-1">
        {enlaces.map((enlace) => (
          <li key={enlace.href}>
            <EnlaceMenuOscuro enlace={enlace} activo={esActivo(enlace, rutaActual)} onNavegar={onNavegar} />
          </li>
        ))}
      </ul>
    </>
  );
}

function PiePersona({
  nombre,
  cargo,
  permiso,
  entornoDemo,
  onSalir,
  saliendo,
}: {
  nombre: string;
  cargo: string | null;
  permiso: Permiso;
  entornoDemo: boolean;
  onSalir: () => void;
  saliendo: boolean;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="text-sm">
        <p className="font-semibold text-sobre-grafito">{TEXTO_PERMISO[permiso]}</p>
        {entornoDemo ? <p className="mt-1 text-cian-claro">Entorno de demostración</p> : null}
      </div>
      <p className="text-sm text-sobre-grafito-suave">
        <span className="sr-only">Sesión de </span>
        {nombre}
        {cargo ? <span className="block text-xs">{cargo}</span> : null}
      </p>
      <button type="button" className={BOTON_OSCURO} onClick={onSalir} disabled={saliendo}>
        {saliendo ? "Saliendo…" : "Salir"}
      </button>
    </div>
  );
}

/**
 * Marco de las pantallas con sesión (diseño de Figma): barra lateral grafito en escritorio; en
 * celular la barra se pliega tras el botón «Menú» y abajo quedan los atajos principales.
 */
export function MarcoPrivado({
  nombre,
  cargo = null,
  permiso,
  entornoDemo = false,
  enlaces,
  rutaActual,
  onSalir,
  saliendo,
  children,
}: {
  nombre: string;
  /** Qué hace la persona en la empresa; se muestra bajo el nombre. */
  cargo?: string | null;
  permiso: Permiso;
  /** Muestra «Entorno de demostración» bajo el permiso. */
  entornoDemo?: boolean;
  enlaces: readonly EntradaMenu[];
  rutaActual: string;
  onSalir: () => void;
  saliendo: boolean;
  children: ReactNode;
}) {
  // El menú del celular queda abierto solo en la ruta donde se abrió: al navegar se cierra solo.
  const [abiertoEn, setAbiertoEn] = useState<string | null>(null);
  const abierto = abiertoEn === rutaActual;
  const boton = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const atajos = enlaces.filter((e) => e.atajo);
  const pie = { nombre, cargo, permiso, entornoDemo, onSalir, saliendo };

  useEffect(() => {
    if (abierto) panel.current?.querySelector<HTMLElement>("a")?.focus();
  }, [abierto]);

  function cerrar() {
    setAbiertoEn(null);
    boton.current?.focus();
  }

  function alTeclear(evento: KeyboardEvent) {
    if (evento.key === "Escape" && abierto) cerrar();
  }

  return (
    <AvisosProvider>
      <div className="flex flex-1">
        <a
          href="#contenido"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-30 focus:rounded-lg focus:bg-superficie focus:p-3"
        >
          Saltar al contenido
        </a>

        <aside className="zona-oscura sticky top-0 hidden h-dvh w-60 shrink-0 flex-col overflow-y-auto bg-grafito px-5 py-7 text-sobre-grafito md:flex">
          <Marca />
          <nav aria-label="Principal" className="mt-10">
            <ListaMenu enlaces={enlaces} rutaActual={rutaActual} />
          </nav>
          <div className="mt-auto pt-6">
            <PiePersona {...pie} />
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="md:hidden" onKeyDown={alTeclear}>
          <header className="zona-oscura flex items-center justify-between gap-3 bg-grafito px-4 py-3 text-sobre-grafito">
            <Marca tamano="pequena" />
            <button
              ref={boton}
              type="button"
              className={BOTON_OSCURO}
              aria-expanded={abierto}
              aria-controls="menu-celular"
              onClick={() => setAbiertoEn(abierto ? null : rutaActual)}
            >
              Menú
            </button>
          </header>
          {/* El menú entra y sale por la izquierda, sobre un velo que lo cierra al tocarlo. */}
          <div
            aria-hidden="true"
            onClick={cerrar}
            className={`fixed inset-0 z-30 bg-velo transition-opacity duration-200 ease-salida ${
              abierto ? "opacity-100" : "pointer-events-none opacity-0"
            }`}
          />
          <div
            id="menu-celular"
            aria-hidden={!abierto}
            inert={!abierto}
            className={`zona-oscura se-mueve fixed inset-y-0 left-0 z-40 flex w-72 max-w-full flex-col overflow-y-auto bg-grafito px-5 py-6 text-sobre-grafito shadow-lg transition-[translate,opacity] duration-200 ease-salida ${
              abierto ? "translate-x-0 opacity-100" : "-translate-x-full opacity-0"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <Marca tamano="pequena" />
              <button type="button" className={BOTON_OSCURO} onClick={cerrar}>
                Cerrar menú
              </button>
            </div>
            <nav aria-label="Menú" className="mt-8" ref={panel}>
              <ListaMenu enlaces={enlaces} rutaActual={rutaActual} onNavegar={() => setAbiertoEn(null)} />
            </nav>
            <div className="mt-auto border-t border-white/15 pt-5">
              <PiePersona {...pie} />
            </div>
          </div>
        </div>
        <main id="contenido" className="mx-auto w-full max-w-contenido flex-1 px-4 pb-28 pt-6 md:px-8 md:pb-10">
            {children}
          </main>
        </div>

        <nav
          aria-label="Atajos"
          className="fixed inset-x-0 bottom-0 z-20 border-t border-linea bg-superficie pb-[env(safe-area-inset-bottom)] md:hidden"
        >
          <ul className="grid" style={{ gridTemplateColumns: `repeat(${Math.max(atajos.length, 1)}, minmax(0, 1fr))` }}>
            {atajos.map((enlace) => {
              const activo = esActivo(enlace, rutaActual);
              return (
                <li key={enlace.href}>
                  <Link
                    href={enlace.href}
                    aria-current={activo ? "page" : undefined}
                    className={`flex min-h-14 items-center justify-center border-t-4 px-1 text-center text-sm font-bold uppercase tracking-wide no-underline ${PRESIONAR} ${
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
    </AvisosProvider>
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
