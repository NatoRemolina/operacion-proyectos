import type { AuthRepository } from "@/features/auth/domain/auth";
import { crearAuthHttp } from "@/features/auth/infrastructure/auth-http";
import { crearAuthMemoria } from "@/features/auth/infrastructure/auth-memoria";
import type { GastosRepository } from "@/features/gastos/domain/gastos";
import { crearGastosHttp } from "@/features/gastos/infrastructure/gastos-http";
import { crearGastosMemoria } from "@/features/gastos/infrastructure/gastos-memoria";
import type { ViajesRepository } from "@/features/viajes/domain/viajes";
import { crearViajesHttp } from "@/features/viajes/infrastructure/viajes-http";
import { crearViajesMemoria } from "@/features/viajes/infrastructure/viajes-memoria";
import type { FuenteDatos } from "@/config/configuracion";
import type { ModoDemo } from "@/shared/application/modo";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { crearSesionMemoria } from "@/shared/infrastructure/memoria";
import { CUENTA_DEMO, GASTOS_DEMO, VIAJES_DEMO, VIAJES_PROPIOS_DEMO } from "./datos-demo";

export interface Repositorios {
  auth: AuthRepository;
  viajes: ViajesRepository;
  gastos: GastosRepository;
  demo: ModoDemo | null;
}

/** Único punto que elige la implementación concreta de cada puerto. */
export function crearRepositorios(fuente: FuenteDatos, baseApi: string): Repositorios {
  if (fuente === "demo") {
    const sesion = crearSesionMemoria({
      almacen: typeof window === "undefined" ? undefined : window.sessionStorage,
    });
    const latenciaMs = 450;
    return {
      auth: crearAuthMemoria({ cuentas: [CUENTA_DEMO], sesion, latenciaMs: 150 }),
      viajes: crearViajesMemoria({ viajes: VIAJES_DEMO, sesion, latenciaMs }),
      gastos: crearGastosMemoria({
        gastos: GASTOS_DEMO,
        viajesPropios: VIAJES_PROPIOS_DEMO,
        sesion,
        latenciaMs: 1200,
      }),
      demo: {
        cuentas: [
          { correo: CUENTA_DEMO.persona.correo, clave: CUENTA_DEMO.clave, descripcion: "Piloto" },
        ],
      },
    };
  }
  const cliente = crearClienteHttp(baseApi);
  return {
    auth: crearAuthHttp(cliente),
    viajes: crearViajesHttp(cliente),
    gastos: crearGastosHttp(cliente),
    demo: null,
  };
}
