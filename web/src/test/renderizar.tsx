import type { ReactElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { AuthRepository } from "@/features/auth/domain/auth";
import { AuthRepositoryProvider } from "@/features/auth/application/sesion";
import type { GastosRepository } from "@/features/gastos/domain/gastos";
import { GastosRepositoryProvider } from "@/features/gastos/application/gastos";
import { crearGastosMemoria } from "@/features/gastos/infrastructure/gastos-memoria";
import type { ViajesRepository } from "@/features/viajes/domain/viajes";
import { ViajesRepositoryProvider } from "@/features/viajes/application/viajes";
import { crearViajesMemoria } from "@/features/viajes/infrastructure/viajes-memoria";
import { IdentidadProvider } from "@/shared/application/identidad";
import type { CotizarRepository } from "@/features/cotizar/domain/cotizar";
import { CotizarRepositoryProvider } from "@/features/cotizar/application/cotizar";
import { crearCotizarMemoria } from "@/features/cotizar/infrastructure/cotizar-memoria";
import { FORMULARIO_EJEMPLO } from "@/features/cotizar/infrastructure/ejemplo-moab";

const authNoUsado: AuthRepository = {
  entrar: () => Promise.reject(new Error("no usado")),
  quienSoy: () => Promise.resolve(null),
  salir: () => Promise.resolve(),
};

/**
 * Monta una pantalla con los puertos que la prueba elija, igual que hace `composition`
 * en la aplicación: la interfaz no cambia, solo la fuente de datos.
 */
export function renderizarConFuente(
  ui: ReactElement,
  fuente: {
    gastos?: GastosRepository;
    viajes?: ViajesRepository;
    auth?: AuthRepository;
    cotizar?: CotizarRepository;
    personaId?: number;
  } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthRepositoryProvider repositorio={fuente.auth ?? authNoUsado}>
        <ViajesRepositoryProvider repositorio={fuente.viajes ?? crearViajesMemoria({ viajes: [] })}>
          <GastosRepositoryProvider repositorio={fuente.gastos ?? crearGastosMemoria({})}>
            <CotizarRepositoryProvider
              repositorio={fuente.cotizar ?? crearCotizarMemoria({ formulario: FORMULARIO_EJEMPLO })}
            >
              <IdentidadProvider personaId={fuente.personaId ?? 1}>{ui}</IdentidadProvider>
            </CotizarRepositoryProvider>
          </GastosRepositoryProvider>
        </ViajesRepositoryProvider>
      </AuthRepositoryProvider>
    </QueryClientProvider>,
  );
}
