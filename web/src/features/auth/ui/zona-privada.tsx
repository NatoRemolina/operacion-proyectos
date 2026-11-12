"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { IdentidadProvider } from "@/shared/application/identidad";
import { Cargando } from "@/shared/ui/estado";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { MarcoPrivado, type EnlaceMenu } from "@/shared/ui/marco-privado";
import { useSalir, useSesion } from "../application/sesion";

const ENLACES: readonly EnlaceMenu[] = [
  { href: "/viajes", texto: "Mis viajes", corto: "Viajes" },
  { href: "/gastos", texto: "Mis gastos", corto: "Gastos" },
  { href: "/gastos/nuevo", texto: "Cargar un gasto", corto: "Cargar" },
];

/**
 * Comprueba la sesión antes de mostrar una pantalla privada. Es solo experiencia de uso:
 * los permisos los aplica la API en cada petición.
 */
export function ZonaPrivada({ children }: { children: ReactNode }) {
  const router = useRouter();
  const ruta = usePathname();
  const sesion = useSesion();
  const salir = useSalir();
  // Al salir a propósito se va a /entrar sin «volver»; esto cubre la sesión que vence sola.
  const sinSesion = sesion.isSuccess && sesion.data === null && salir.isIdle;

  useEffect(() => {
    if (sinSesion) router.replace(`/entrar?volver=${encodeURIComponent(ruta)}`);
  }, [sinSesion, ruta, router]);

  if (sesion.isPending) {
    return (
      <main id="contenido" className="mx-auto w-full max-w-contenido px-4">
        <Cargando texto="Comprobando tu sesión…" />
      </main>
    );
  }
  if (sesion.isError) {
    return (
      <main id="contenido" className="mx-auto w-full max-w-contenido px-4 py-6">
        <h1 className="mb-4 text-2xl font-bold">No pudimos comprobar tu sesión</h1>
        <ErrorConsulta error={sesion.error} onReintentar={() => void sesion.refetch()} />
      </main>
    );
  }
  if (!sesion.data) {
    return (
      <main id="contenido" className="mx-auto w-full max-w-contenido px-4">
        <Cargando texto="Te llevamos a la pantalla de ingreso…" />
      </main>
    );
  }

  return (
    <MarcoPrivado
      nombre={sesion.data.nombre}
      cargo={sesion.data.cargo}
      enlaces={ENLACES}
      rutaActual={ruta}
      saliendo={salir.isPending}
      onSalir={() => salir.mutate(undefined, { onSettled: () => router.replace("/entrar") })}
    >
      <IdentidadProvider personaId={sesion.data.id}>{children}</IdentidadProvider>
    </MarcoPrivado>
  );
}
