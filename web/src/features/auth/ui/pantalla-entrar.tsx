"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useModoDemo } from "@/shared/application/modo";
import { Marca } from "@/shared/ui/marco-privado";
import { useEntrar, useSesion } from "../application/sesion";
import { destinoSeguro } from "../domain/auth";
import { FormularioEntrar } from "./formulario-entrar";

/**
 * Ilustración del panel de bienvenida (diseño de Figma): un viaje de ejemplo con la ruta de muestra del repositorio,
 * sin datos de ninguna persona. Es decorativa: los lectores de pantalla la omiten.
 */
function TarjetaIlustrativa() {
  return (
    <div aria-hidden="true" className="max-w-sm rounded-tarjeta bg-marca p-5 text-sobre-marca shadow-flotante">
      <span className="inline-block rounded-md bg-marca-suave px-2 py-1 text-xs font-semibold tabular-nums text-marca">
        V-2026-0012 · Aprobado
      </span>
      <p className="mt-4 text-2xl font-bold">Miami → Moab</p>
      <p className="mt-1 text-sm">Producción inmobiliaria · 8 – 11 dic 2026</p>
      <hr className="my-4 border-sobre-marca/40" />
      <div className="flex items-baseline justify-between gap-4 text-sm">
        <span className="font-semibold">Presupuesto aprobado</span>
        <span className="font-bold tabular-nums">USD 1.153,00</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-sobre-marca/25">
        <div className="h-full w-[31%] rounded-full bg-sobre-marca" />
      </div>
      <p className="mt-3 text-sm">Cada gasto, asociado a su viaje.</p>
    </div>
  );
}

export function PantallaEntrar() {
  const router = useRouter();
  const destino = destinoSeguro(useSearchParams().get("volver"));
  const sesion = useSesion();
  const entrar = useEntrar();
  const demo = useModoDemo();

  useEffect(() => {
    if (sesion.data) router.replace(destino);
  }, [sesion.data, destino, router]);

  // Mensaje genérico: no revela si el correo existe.
  const error = entrar.error
    ? entrar.error.tipo === "credenciales"
      ? "El correo o la contraseña no son correctos."
      : entrar.error.message
    : null;

  return (
    <div className="grid flex-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <section
        aria-label="Presentación"
        className="zona-oscura hidden flex-col justify-between gap-10 bg-grafito px-12 py-14 text-sobre-grafito lg:flex"
      >
        <Marca />
        <div className="flex flex-col gap-8">
          <div>
            <p className="text-4xl font-bold xl:text-5xl">
              Tu operación,
              <br />
              en una sola vista.
            </p>
            <p className="mt-5 max-w-sm text-sobre-grafito-suave">
              Planea cada viaje. Conserva cada soporte. Decide con información clara.
            </p>
          </div>
          <TarjetaIlustrativa />
        </div>
        <p className="text-xs font-semibold tracking-wider text-cian-claro">VIAJES / GASTOS / CONTROL</p>
      </section>

      <main id="contenido" className="flex flex-col justify-center bg-superficie px-4 py-10 sm:px-10">
        <div className="mx-auto w-full max-w-md">
          <div className="zona-oscura mb-8 inline-block rounded-lg bg-grafito px-4 py-3 text-sobre-grafito lg:hidden">
            <Marca tamano="pequena" />
          </div>
          <h1 className="text-3xl font-bold">Bienvenido a Inflight</h1>
          <p className="mb-6 mt-2 text-texto-secundario">Ingresa con tu cuenta de la empresa.</p>
          <FormularioEntrar
            enviando={entrar.isPending}
            error={error}
            onEntrar={(datos) => entrar.mutate(datos, { onSuccess: () => router.replace(destino) })}
            ayuda={
              <>
                <p className="text-sm text-texto-secundario">
                  ¿Necesitas acceso? Contacta al administrador.
                </p>
                {demo ? (
                  <div className="rounded-lg border border-aviso bg-aviso-suave p-3 text-sm">
                    <p className="font-bold text-aviso">Cuentas de demostración</p>
                    <ul className="mt-1">
                      {demo.cuentas.map((c) => (
                        <li key={c.correo}>
                          {c.descripcion}: <code>{c.correo}</code> / <code>{c.clave}</code>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            }
          />
        </div>
      </main>
    </div>
  );
}
