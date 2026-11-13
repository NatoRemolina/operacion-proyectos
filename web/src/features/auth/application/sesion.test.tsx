import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { AuthRepository } from "../domain/auth";
import { AuthRepositoryProvider, useSalir } from "./sesion";

function montarSalir(salir: () => Promise<void>) {
  const repositorio: AuthRepository = { entrar: () => Promise.reject(new Error("sin uso")), quienSoy: () => Promise.resolve(null), salir };
  const cliente = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const envoltura = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={cliente}>
      <AuthRepositoryProvider repositorio={repositorio}>{children}</AuthRepositoryProvider>
    </QueryClientProvider>
  );
  return renderHook(() => useSalir(), { wrapper: envoltura }).result;
}

function guardarConversaciones() {
  window.sessionStorage.setItem("asistente:v1:7", "[]");
  window.sessionStorage.setItem("asistente:v2:9", "[]");
  window.sessionStorage.setItem("otra-cosa", "se conserva");
}

afterEach(() => window.sessionStorage.clear());

describe("salir", () => {
  it("borra de la pestaña las conversaciones del asistente y nada más", async () => {
    guardarConversaciones();
    const salir = montarSalir(() => Promise.resolve());
    await act(() => salir.current.mutateAsync());
    expect(window.sessionStorage.getItem("asistente:v1:7")).toBeNull();
    expect(window.sessionStorage.getItem("asistente:v2:9")).toBeNull();
    expect(window.sessionStorage.getItem("otra-cosa")).toBe("se conserva");
  });

  it("las borra aunque el servidor no responda al salir", async () => {
    guardarConversaciones();
    const salir = montarSalir(() => Promise.reject(new Error("sin red")));
    await act(async () => {
      await salir.current.mutateAsync().catch(() => undefined);
    });
    expect(window.sessionStorage.getItem("asistente:v1:7")).toBeNull();
  });
});
