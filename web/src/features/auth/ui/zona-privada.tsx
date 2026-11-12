"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { IdentidadProvider } from "@/shared/application/identidad";
import { useModoDemo } from "@/shared/application/modo";
import { PlataformaProvider } from "@/shared/application/plataforma";
import { menuPara } from "@/shared/domain/navegacion";
import { Cargando } from "@/shared/ui/estado";
import { ErrorConsulta } from "@/shared/ui/error-consulta";
import { MarcoPrivado } from "@/shared/ui/marco-privado";
import { useSalir, useSesion, useVigilarSesionVencida } from "../application/sesion";

/**
 * Comprueba la sesión antes de mostrar una pantalla privada. Es solo experiencia de uso:
 * los permisos los aplica la API en cada petición.
 */
export function ZonaPrivada({
  plataforma,
  children,
}: {
  /** Origen de las pantallas actuales de la plataforma; vacío si no está configurado (entonces no se enlazan). */
  plataforma: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const demo = useModoDemo();
  const ruta = usePathname();
  const sesion = useSesion();
  const salir = useSalir();
  useVigilarSesionVencida();
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
      permiso={sesion.data.rol}
      entornoDemo={demo !== null || sesion.data.demostracion === true}
      enlaces={menuPara(sesion.data.rol, plataforma)}
      rutaActual={ruta}
      saliendo={salir.isPending}
      onSalir={() => salir.mutate(undefined, { onSettled: () => router.replace("/entrar") })}
    >
      <IdentidadProvider personaId={sesion.data.id} permiso={sesion.data.rol}>
        <PlataformaProvider origen={plataforma}>{children}</PlataformaProvider>
      </IdentidadProvider>
    </MarcoPrivado>
  );
}
