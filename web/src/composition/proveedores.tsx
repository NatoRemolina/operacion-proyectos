"use client";

import { useState, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { AdministracionRepositoryProvider } from "@/features/administracion/application/administracion";
import { AsistenteRepositoryProvider } from "@/features/asistente/application/asistente";
import { AuthRepositoryProvider } from "@/features/auth/application/sesion";
import { CotizarRepositoryProvider } from "@/features/cotizar/application/cotizar";
import { CuentaRepositoryProvider } from "@/features/cuenta/application/cuenta";
import { GastosRepositoryProvider } from "@/features/gastos/application/gastos";
import { KpisRepositoryProvider } from "@/features/kpis/application/kpis";
import { MonitoreoRepositoryProvider } from "@/features/monitoreo/application/monitoreo";
import { ProyectosRepositoryProvider } from "@/features/proyectos/application/proyectos";
import { UsuariosRepositoryProvider } from "@/features/usuarios/application/usuarios";
import { VuelosRepositoryProvider } from "@/features/vuelos/application/vuelos";
import { ViajesRepositoryProvider } from "@/features/viajes/application/viajes";
import { leerBaseApi, type FuenteDatos } from "@/config/configuracion";
import { crearQueryClient } from "@/shared/application/consultas";
import { ModoProvider } from "@/shared/application/modo";
import { AvisoDemo } from "@/shared/ui/marco-privado";
import { crearRepositorios } from "./repositorios";

/**
 * Crea una sola vez (por pestaña) los repositorios y el QueryClient y los inyecta.
 * Las instancias son estables: no se recrean en cada render.
 */
export function Proveedores({ fuente, children }: { fuente: FuenteDatos; children: ReactNode }) {
  const [repositorios] = useState(() =>
    crearRepositorios(fuente, leerBaseApi(process.env.NEXT_PUBLIC_API_BASE)),
  );
  const [queryClient] = useState(crearQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <ModoProvider demo={repositorios.demo}>
        <AuthRepositoryProvider repositorio={repositorios.auth}>
          <ViajesRepositoryProvider repositorio={repositorios.viajes}>
            <GastosRepositoryProvider repositorio={repositorios.gastos}>
              <CotizarRepositoryProvider repositorio={repositorios.cotizar}>
                <AdministracionRepositoryProvider repositorio={repositorios.administracion}>
                  <AsistenteRepositoryProvider repositorio={repositorios.asistente}>
                    <KpisRepositoryProvider repositorio={repositorios.kpis}>
                      <MonitoreoRepositoryProvider repositorio={repositorios.monitoreo}>
                        <VuelosRepositoryProvider repositorio={repositorios.vuelos}>
                          <ProyectosRepositoryProvider repositorio={repositorios.proyectos}>
                            <UsuariosRepositoryProvider repositorio={repositorios.usuarios}>
                              <CuentaRepositoryProvider repositorio={repositorios.cuenta}>
                                {repositorios.demo ? <AvisoDemo /> : null}
                                {children}
                              </CuentaRepositoryProvider>
                            </UsuariosRepositoryProvider>
                          </ProyectosRepositoryProvider>
                        </VuelosRepositoryProvider>
                      </MonitoreoRepositoryProvider>
                    </KpisRepositoryProvider>
                  </AsistenteRepositoryProvider>
                </AdministracionRepositoryProvider>
              </CotizarRepositoryProvider>
            </GastosRepositoryProvider>
          </ViajesRepositoryProvider>
        </AuthRepositoryProvider>
      </ModoProvider>
    </QueryClientProvider>
  );
}
