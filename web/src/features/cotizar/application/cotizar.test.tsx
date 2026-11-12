import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { IdentidadProvider } from "@/shared/application/identidad";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { BORRADOR_VACIO, borradorDeEjemplo, pedidoDesdeBorrador, type CotizarRepository } from "../domain/cotizar";
import { crearCotizarMemoria } from "../infrastructure/cotizar-memoria";
import { COTIZACION_MOAB, FORMULARIO_EJEMPLO } from "../infrastructure/ejemplo-moab";
import { CotizarRepositoryProvider, useCotizar, useDecidir } from "./cotizar";

function envoltorio(repositorio: CotizarRepository) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return function Envoltorio({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <CotizarRepositoryProvider repositorio={repositorio}>
          <IdentidadProvider personaId={1}>{children}</IdentidadProvider>
        </CotizarRepositoryProvider>
      </QueryClientProvider>
    );
  };
}

const PEDIDO = pedidoDesdeBorrador(borradorDeEjemplo(BORRADOR_VACIO), 1);

describe("idempotencia al cotizar y decidir", () => {
  it("reintentar la misma cotización usa la misma clave; otra cotización, una nueva", async () => {
    const base = crearCotizarMemoria({ formulario: FORMULARIO_EJEMPLO, guardadas: [COTIZACION_MOAB] });
    const cotizar = vi
      .fn<CotizarRepository["cotizar"]>()
      .mockRejectedValueOnce(new ErrorDeAplicacion("red"))
      .mockResolvedValue(COTIZACION_MOAB);
    const { result } = renderHook(() => useCotizar(), { wrapper: envoltorio({ ...base, cotizar }) });
    await act(() => result.current.mutateAsync(PEDIDO).catch(() => null));
    await act(() => result.current.mutateAsync(PEDIDO));
    expect(cotizar.mock.calls[1]![1]).toBe(cotizar.mock.calls[0]![1]);
    await act(() => result.current.mutateAsync({ ...PEDIDO, ida: "2026-12-09" }));
    expect(cotizar.mock.calls[2]![1]).not.toBe(cotizar.mock.calls[0]![1]);
  });

  it("reintentar la misma decisión usa la misma clave", async () => {
    const base = crearCotizarMemoria({ formulario: FORMULARIO_EJEMPLO, guardadas: [COTIZACION_MOAB] });
    const decidir = vi
      .fn<CotizarRepository["decidir"]>()
      .mockRejectedValueOnce(new ErrorDeAplicacion("servidor"))
      .mockResolvedValue(COTIZACION_MOAB);
    const { result } = renderHook(() => useDecidir(COTIZACION_MOAB.id), { wrapper: envoltorio({ ...base, decidir }) });
    const decision = { vuelo_id: 1, hotel_id: null, motivo: "", razones: [] };
    await act(() => result.current.mutateAsync(decision).catch(() => null));
    await act(() => result.current.mutateAsync(decision));
    expect(decidir.mock.calls[0]![2]).toBeTruthy();
    expect(decidir.mock.calls[1]![2]).toBe(decidir.mock.calls[0]![2]);
  });
});
