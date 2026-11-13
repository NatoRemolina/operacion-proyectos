import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IdentidadProvider } from "@/shared/application/identidad";
import { crearUsuariosMemoria } from "../infrastructure/usuarios-memoria";
import { usuarioDePrueba } from "../test/fabricas";
import { UsuariosRepositoryProvider, useAccionCuenta } from "./usuarios";

const queryClient = new QueryClient();
const repo = crearUsuariosMemoria({ usuarios: [usuarioDePrueba({ id: 2 })], permiso: "admin", yo: 1 });

function envoltorio({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <UsuariosRepositoryProvider repositorio={repo}>
        <IdentidadProvider personaId={1} permiso="admin">
          {children}
        </IdentidadProvider>
      </UsuariosRepositoryProvider>
    </QueryClientProvider>
  );
}

describe("acciones sobre una cuenta", () => {
  it("la contraseña enviada no queda guardada en el estado de la acción al terminar", async () => {
    const { result } = renderHook(() => useAccionCuenta((repo, clave: string) => repo.restablecerClave(2, clave)), {
      wrapper: envoltorio,
    });
    let exito = false;
    act(() => result.current.mutate("clave-nueva-456789", { onSuccess: () => (exito = true) }));
    await waitFor(() => expect(exito).toBe(true));
    await waitFor(() => expect(result.current.variables).toBeUndefined());
  });
});
