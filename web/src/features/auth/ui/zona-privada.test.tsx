import { screen, waitFor, within } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ModoProvider } from "@/shared/application/modo";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { personaDePrueba } from "@/test/fabricas";
import type { AuthRepository, Persona } from "../domain/auth";
import { ZonaPrivada } from "./zona-privada";

const navegacion = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/viajes",
  useRouter: () => navegacion,
}));

function auth(persona: Persona): AuthRepository {
  return {
    entrar: () => Promise.resolve(persona),
    quienSoy: () => Promise.resolve(persona),
    salir: () => Promise.resolve(),
  };
}

async function barraPara(persona: Persona, demo = false) {
  renderizarConFuente(
    <ModoProvider demo={demo ? { cuentas: [] } : null}>
      <ZonaPrivada plataforma="http://127.0.0.1:8000">
        <p>contenido</p>
      </ZonaPrivada>
    </ModoProvider>,
    { auth: auth(persona), personaId: persona.id },
  );
  return screen.findByRole("navigation", { name: "Principal" });
}

describe("Zona privada", () => {
  it("administración ve el resumen y las pantallas actuales en el menú", async () => {
    const barra = await barraPara(personaDePrueba({ rol: "admin" }));
    expect(within(barra).getByRole("link", { name: "Resumen" })).toHaveAttribute("href", "/resumen");
    expect(within(barra).getByRole("link", { name: "Proyectos" })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8000/admin/proyectos",
    );
  });

  it("el gestor no ve el resumen y sí «Cotizar viaje»", async () => {
    const barra = await barraPara(personaDePrueba({ rol: "gestor" }));
    expect(within(barra).queryByRole("link", { name: "Resumen" })).not.toBeInTheDocument();
    expect(within(barra).getByRole("link", { name: "Cotizar viaje" })).toHaveAttribute("href", "/cotizar");
  });

  it("si el servidor dice que el entorno es de demostración, la barra lo indica", async () => {
    await barraPara(personaDePrueba({ rol: "admin", demostracion: true }));
    expect(screen.getAllByText("Entorno de demostración").length).toBeGreaterThan(0);
  });

  it("con datos de demostración la barra dice «Entorno de demostración»", async () => {
    await barraPara(personaDePrueba({ rol: "colaborador" }), true);
    expect(screen.getAllByText("Entorno de demostración").length).toBeGreaterThan(0);
  });
});

function LecturaVencida() {
  useQuery({
    queryKey: ["persona", 1, "algo"],
    queryFn: () => Promise.reject(new ErrorDeAplicacion("sesion_vencida")),
    retry: false,
  });
  return <p>contenido</p>;
}

describe("Zona privada con la sesión vencida", () => {
  it("si una lectura descubre que la sesión venció, lleva a entrar y regresa a la misma página", async () => {
    navegacion.replace.mockClear();
    renderizarConFuente(
      <ZonaPrivada plataforma="">
        <LecturaVencida />
      </ZonaPrivada>,
      { auth: auth(personaDePrueba({ rol: "colaborador" })) },
    );
    await waitFor(() => expect(navegacion.replace).toHaveBeenCalledWith(`/entrar?volver=${encodeURIComponent("/viajes")}`));
  });
});
