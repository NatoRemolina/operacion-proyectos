import type { AdministracionRepository } from "@/features/administracion/domain/administracion";
import { crearAdministracionHttp } from "@/features/administracion/infrastructure/administracion-http";
import { crearAdministracionMemoria } from "@/features/administracion/infrastructure/administracion-memoria";
import type { AsistenteRepository } from "@/features/asistente/domain/asistente";
import { crearAsistenteHttp } from "@/features/asistente/infrastructure/asistente-http";
import { crearAsistenteMemoria } from "@/features/asistente/infrastructure/asistente-memoria";
import type { AuthRepository } from "@/features/auth/domain/auth";
import type { CotizarRepository } from "@/features/cotizar/domain/cotizar";
import { crearCotizarHttp } from "@/features/cotizar/infrastructure/cotizar-http";
import { crearCotizarMemoria } from "@/features/cotizar/infrastructure/cotizar-memoria";
import { COTIZACION_MOAB, LUGARES_EJEMPLO, SOLO_GOOGLE } from "@/features/cotizar/infrastructure/ejemplo-moab";
import { crearAuthHttp } from "@/features/auth/infrastructure/auth-http";
import { crearAuthMemoria } from "@/features/auth/infrastructure/auth-memoria";
import type { CuentaRepository } from "@/features/cuenta/domain/cuenta";
import { crearCuentaHttp } from "@/features/cuenta/infrastructure/cuenta-http";
import { crearCuentaMemoria } from "@/features/cuenta/infrastructure/cuenta-memoria";
import type { GastosRepository } from "@/features/gastos/domain/gastos";
import { crearGastosHttp } from "@/features/gastos/infrastructure/gastos-http";
import { crearGastosMemoria } from "@/features/gastos/infrastructure/gastos-memoria";
import type { ProyectosRepository } from "@/features/proyectos/domain/proyectos";
import { crearProyectosHttp } from "@/features/proyectos/infrastructure/proyectos-http";
import { crearProyectosMemoria } from "@/features/proyectos/infrastructure/proyectos-memoria";
import type { UsuariosRepository } from "@/features/usuarios/domain/usuarios";
import { crearUsuariosHttp } from "@/features/usuarios/infrastructure/usuarios-http";
import { crearUsuariosMemoria } from "@/features/usuarios/infrastructure/usuarios-memoria";
import type { ViajesRepository } from "@/features/viajes/domain/viajes";
import { crearViajesHttp } from "@/features/viajes/infrastructure/viajes-http";
import { crearViajesMemoria } from "@/features/viajes/infrastructure/viajes-memoria";
import type { KpisRepository } from "@/features/kpis/domain/kpis";
import { crearKpisHttp } from "@/features/kpis/infrastructure/kpis-http";
import { crearKpisMemoria } from "@/features/kpis/infrastructure/kpis-memoria";
import type { MonitoreoRepository } from "@/features/monitoreo/domain/monitoreo";
import { crearMonitoreoHttp } from "@/features/monitoreo/infrastructure/monitoreo-http";
import { crearMonitoreoMemoria } from "@/features/monitoreo/infrastructure/monitoreo-memoria";
import type { VuelosRepository } from "@/features/vuelos/domain/vuelos";
import { crearVuelosHttp } from "@/features/vuelos/infrastructure/vuelos-http";
import { crearVuelosMemoria } from "@/features/vuelos/infrastructure/vuelos-memoria";
import type { FuenteDatos } from "@/config/configuracion";
import type { ModoDemo } from "@/shared/application/modo";
import { crearClienteHttp } from "@/shared/infrastructure/cliente-http";
import { crearSesionMemoria } from "@/shared/infrastructure/memoria";
import { CUENTA_DEMO, GASTOS_DEMO, VIAJES_DEMO, VIAJES_PROPIOS_DEMO } from "./datos-demo";

export interface Repositorios {
  auth: AuthRepository;
  viajes: ViajesRepository;
  gastos: GastosRepository;
  cotizar: CotizarRepository;
  administracion: AdministracionRepository;
  asistente: AsistenteRepository;
  kpis: KpisRepository;
  monitoreo: MonitoreoRepository;
  vuelos: VuelosRepository;
  proyectos: ProyectosRepository;
  usuarios: UsuariosRepository;
  cuenta: CuentaRepository;
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
      cotizar: crearCotizarMemoria({
        formulario: {
          proyectos: [
            { id: 31, nombre: "Proyecto de demostración", ciudad: "Moab", inicio: "2026-12-08", fin: "2026-12-11", para_otra_persona: false },
          ],
          viajeros: [{ id: CUENTA_DEMO.persona.id, nombre: CUENTA_DEMO.persona.nombre, base: "Miami", soy_yo: true }],
          viajero_propio_id: CUENTA_DEMO.persona.id,
          elige_viajero: false,
          razones: [
            { clave: "costo_total", texto: "Menor costo total" },
            { clave: "horario", texto: "Mejor horario" },
            { clave: "directo", texto: "Vuelo directo" },
            { clave: "equipaje", texto: "Equipaje del equipo" },
            { clave: "otra", texto: "Otra" },
          ],
          precios_en_vivo: false,
        },
        lugares: Object.values(LUGARES_EJEMPLO).flatMap((l) => l.resultados),
        lugaresGoogle: [SOLO_GOOGLE],
        guardadas: [COTIZACION_MOAB],
        sesion,
        latenciaMs: 120,
        latenciaBusquedaMs: 2500,
      }),
      // La cuenta de demostración es de colaboración: el resumen responde «sin permiso», como la API.
      administracion: crearAdministracionMemoria({ sesion, latenciaMs }),
      // Igual que el resumen: el asistente es de administración y la cuenta de demostración no lo es.
      asistente: crearAsistenteMemoria({ sesion, latenciaMs }),
      // Tablero de administración: la cuenta de demostración no lo ve, como en la API.
      kpis: crearKpisMemoria({ sesion, latenciaMs }),
      monitoreo: crearMonitoreoMemoria({ sesion, latenciaMs }),
      vuelos: crearVuelosMemoria({ sesion, latenciaMs }),
      // La cuenta de demostración es de colaboración: proyectos responde «sin permiso», como la API.
      proyectos: crearProyectosMemoria({ sesion, latenciaMs }),
      // Usuarios es solo de administración: con la cuenta de demostración responde «sin permiso», como la API.
      usuarios: crearUsuariosMemoria({ sesion, latenciaMs }),
      cuenta: crearCuentaMemoria({
        cuenta: {
          persona: CUENTA_DEMO.persona,
          rol_texto: "colaborador",
          telegram: { vinculado: false, usuario: null, canal_activo: false },
        },
        clave: CUENTA_DEMO.clave,
        sesion,
        latenciaMs,
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
    cotizar: crearCotizarHttp(cliente),
    administracion: crearAdministracionHttp(cliente),
    asistente: crearAsistenteHttp(cliente),
    kpis: crearKpisHttp(cliente),
    monitoreo: crearMonitoreoHttp(cliente),
    vuelos: crearVuelosHttp(cliente),
    proyectos: crearProyectosHttp(cliente),
    usuarios: crearUsuariosHttp(cliente),
    cuenta: crearCuentaHttp(cliente),
    demo: null,
  };
}
