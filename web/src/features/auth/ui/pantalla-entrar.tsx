"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useModoDemo } from "@/shared/application/modo";
import { Marca } from "@/shared/ui/marco-privado";
import { useEntrar, useSesion } from "../application/sesion";
import { destinoSeguro } from "../domain/auth";
import { FormularioEntrar } from "./formulario-entrar";
import { IlustracionRuta } from "./ilustracion-ruta";

function Icono({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="mt-0.5 size-6 shrink-0 text-marca"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

/** Lo que resuelven los dos retos, en palabras de quien lo usa. */
const BENEFICIOS = [
  {
    titulo: "Costo total del viaje",
    texto: "Tiquete, equipaje con baterías, riesgo de cambio y millas, en una cifra.",
    icono: (
      <>
        <circle cx="5" cy="18" r="2" />
        <circle cx="19" cy="6" r="2" />
        <path d="M6.5 16.5C9 9 13 7.5 17 6.5" strokeDasharray="2.5 2.5" />
      </>
    ),
  },
  {
    titulo: "Recibos leídos y validados solos",
    texto: "Foto, PDF o correo; las reglas aprueban o piden revisión.",
    icono: (
      <>
        <path d="M6 3h12v18l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5L6 21z" />
        <path d="m9 11 2 2 4-4" />
      </>
    ),
  },
  {
    titulo: "Control por viaje y por proyecto",
    texto: "Presupuesto aprobado frente a gasto real, casi al momento.",
    icono: (
      <>
        <path d="M4 20h16" />
        <path d="M7 16v-5M12 16V6M17 16v-8" />
      </>
    ),
  },
] as const;

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

  // Orden del documento = orden visual en el celular: presentación, formulario, beneficios. En escritorio el
  // formulario ocupa la columna derecha. La presentación no tiene nada enfocable: tras el título, lo primero
  // que alcanza el teclado es el correo.
  return (
    <div className="grid flex-1 bg-carta lg:grid-cols-[minmax(0,1fr)_25rem] lg:grid-rows-[1fr_auto] xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <section
        aria-label="Presentación"
        className="min-w-0 px-4 pb-12 pt-5 sm:px-10 sm:pt-8 lg:col-start-1 lg:row-start-1 lg:pb-2 lg:pl-10 lg:pr-6 lg:pt-8 xl:pl-16 xl:pr-10"
      >
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <Marca fondo="claro" />
        </div>
        <div className="lg:max-w-[38rem]">
        <p className="mt-8 text-balance text-[2.125rem] font-extrabold leading-[1.04] tracking-[-0.035em] sm:text-5xl lg:mt-8 xl:text-[3.25rem]">
          Cada viaje, del presupuesto al último recibo.
        </p>
        <p className="mt-4 max-w-xl text-pretty text-texto-secundario sm:text-lg">
          Cotiza vuelos y hoteles por su costo total, aprueba el presupuesto y deja que cada recibo se lea, se valide y
          llegue solo a su viaje.
        </p>
        <div className="mt-7 lg:mt-6">
          <IlustracionRuta />
        </div>
        </div>
      </section>

      <main
        id="contenido"
        className="relative -mt-6 rounded-t-[1.75rem] bg-superficie px-4 pb-10 pt-8 shadow-hoja sm:px-10 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:mt-0 lg:rounded-none lg:bg-transparent lg:p-0 lg:shadow-none"
      >
        <div className="lg:sticky lg:top-0 lg:flex lg:min-h-dvh lg:items-center lg:justify-center lg:py-10 lg:pr-8 xl:pl-4 xl:pr-14">
          <div className="mx-auto w-full max-w-md lg:rounded-[1.75rem] lg:bg-superficie lg:p-8 lg:shadow-flotante xl:p-10">
            <h1 className="text-3xl font-bold">Ingresa a tu cuenta</h1>
            <p className="mb-6 mt-2 text-texto-secundario">Con el correo y la contraseña que te dio administración.</p>
            <FormularioEntrar
              enviando={entrar.isPending}
              error={error}
              onEntrar={(datos) => entrar.mutate(datos, { onSuccess: () => router.replace(destino) })}
              ayuda={
                <>
                  <p className="text-sm text-texto-secundario">¿Necesitas acceso? Contacta al administrador.</p>
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
        </div>
      </main>

      <section
        aria-label="Qué resuelve la plataforma"
        className="min-w-0 bg-superficie px-4 pb-12 sm:px-10 lg:col-start-1 lg:row-start-2 lg:bg-transparent lg:pb-10 lg:pl-10 lg:pr-6 lg:pt-6 xl:pl-16 xl:pr-10"
      >
        <ul className="mx-auto grid max-w-md gap-6 border-t border-linea pt-8 sm:max-w-none sm:grid-cols-3 lg:border-0 lg:pt-0">
          {BENEFICIOS.map((b) => (
            <li key={b.titulo} className="flex gap-3">
              <Icono>{b.icono}</Icono>
              <div>
                <p className="font-bold leading-snug">{b.titulo}</p>
                <p className="mt-1 text-sm text-texto-secundario">{b.texto}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
