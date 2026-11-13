import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IdentidadProvider } from "@/shared/application/identidad";
import { crearCuentaMemoria } from "../infrastructure/cuenta-memoria";
import { CuentaRepositoryProvider, useCambiarMiClave } from "./cuenta";

const queryClient = new QueryClient();
const repo = crearCuentaMemoria({
  cuenta: {
    persona: { id: 2, codigo: "P-0002", nombre: "Andrés", rol: "colaborador", correo: "a@demo.local", cargo: null },
    rol_texto: "colaborador",
    telegram: { vinculado: false, usuario: null, canal_activo: false },
  },
  clave: "clave-actual-123",
});

function envoltorio({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <CuentaRepositoryProvider repositorio={repo}>
        <IdentidadProvider personaId={2}>{children}</IdentidadProvider>
      </CuentaRepositoryProvider>
    </QueryClientProvider>
  );
}

describe("cambiar mi contraseña", () => {
  it("las contraseñas no quedan en el estado de la acción al terminar", async () => {
    const { result } = renderHook(() => useCambiarMiClave(), { wrapper: envoltorio });
    let exito = false;
    act(() => result.current.mutate({ actual: "clave-actual-123", nueva: "clave-nueva-456789" }, { onSuccess: () => (exito = true) }));
    await waitFor(() => expect(exito).toBe(true));
    await waitFor(() => expect(result.current.variables).toBeUndefined());
  });
});
