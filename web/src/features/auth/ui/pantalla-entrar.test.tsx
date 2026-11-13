import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderizarConFuente } from "@/test/renderizar";
import type { AuthRepository } from "../domain/auth";
import { PantallaEntrar } from "./pantalla-entrar";

const navegacion = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => navegacion,
  useSearchParams: () => new URLSearchParams(),
}));

const sinSesion: AuthRepository = {
  entrar: () => Promise.reject(new Error("no se usa")),
  quienSoy: () => Promise.resolve(null),
  salir: () => Promise.resolve(),
};

function montar() {
  renderizarConFuente(<PantallaEntrar />, { auth: sinSesion });
}

describe("Portada", () => {
  it("el beneficio de los recibos nombra la confirmación HTML", () => {
    montar();
    const beneficios = screen.getByRole("region", { name: "Qué resuelve la plataforma" });
    expect(within(beneficios).getByText(/Foto, PDF, correo o confirmación HTML/)).toBeInTheDocument();
  });

  it("en pantallas angostas, «Ingresar» va arriba de la presentación y apunta al formulario", () => {
    montar();
    const ingresar = screen.getByRole("link", { name: "Ingresar" });
    const formulario = document.getElementById("contenido")!;
    expect(ingresar).toHaveAttribute("href", "#contenido");
    expect(within(formulario).getByRole("heading", { name: "Ingresa a tu cuenta" })).toBeInTheDocument();
    expect(within(formulario).getByLabelText("Correo")).toBeInTheDocument();
    // Solo por debajo de lg: en escritorio el formulario ya se ve al lado y el diseño no cambia.
    expect(ingresar).toHaveClass("lg:hidden");
    const titular = screen.getByText("Cada viaje, del presupuesto al último recibo.");
    expect(ingresar.compareDocumentPosition(titular) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("«Ingresar» baja hasta el formulario y deja el foco en el campo de correo", async () => {
    const desplazar = vi.fn();
    Element.prototype.scrollIntoView = desplazar; // jsdom no lo implementa
    const usuario = userEvent.setup();
    montar();
    await usuario.click(screen.getByRole("link", { name: "Ingresar" }));
    expect(screen.getByLabelText("Correo")).toHaveFocus();
    expect(desplazar.mock.contexts[0]).toBe(document.getElementById("contenido"));
  });

  it("«Ingresar» no deja que el salto al ancla le quite el foco al correo", () => {
    Element.prototype.scrollIntoView = vi.fn();
    montar();
    // El navegador, al ir a #contenido, enfoca el ancla (o la página) y el correo pierde el foco: el clic lo evita.
    const siguioAlAncla = fireEvent.click(screen.getByRole("link", { name: "Ingresar" }));
    expect(siguioAlAncla).toBe(false);
  });
});
