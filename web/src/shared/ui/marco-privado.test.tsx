import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { menuPara } from "@/shared/domain/navegacion";
import { MarcoPrivado } from "./marco-privado";

function marco({
  cargo = null,
  ruta = "/viajes",
  permiso = "admin" as const,
  entornoDemo = false,
}: {
  cargo?: string | null;
  ruta?: string;
  permiso?: "admin" | "gestor" | "colaborador";
  entornoDemo?: boolean;
} = {}) {
  return render(
    <MarcoPrivado
      nombre="Andrés Molina"
      cargo={cargo}
      permiso={permiso}
      entornoDemo={entornoDemo}
      enlaces={menuPara(permiso, "http://127.0.0.1:8000")}
      rutaActual={ruta}
      onSalir={() => {}}
      saliendo={false}
    >
      <p>contenido</p>
    </MarcoPrivado>,
  );
}

function barraLateral() {
  return screen.getByRole("navigation", { name: "Principal" });
}

describe("Marco privado", () => {
  it("muestra el cargo bajo el nombre", () => {
    marco({ cargo: "Pilotaje de dron" });
    expect(screen.getAllByText("Andrés Molina").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pilotaje de dron").length).toBeGreaterThan(0);
  });

  it("sin cargo solo muestra el nombre", () => {
    const { container } = marco({ cargo: null });
    expect(screen.getAllByText("Andrés Molina").length).toBeGreaterThan(0);
    expect(container.textContent).not.toContain("Pilotaje");
  });

  it("la barra lateral lleva la sección «Operaciones» y las entradas del permiso", () => {
    marco({ permiso: "admin" });
    const barra = barraLateral();
    expect(within(barra).getByText("Operaciones")).toBeInTheDocument();
    expect(within(barra).getAllByRole("link").map((a) => a.textContent)).toEqual([
      "Resumen",
      "Cotizar viaje",
      "Viajes",
      "Gastos",
      "Proyectos",
      "Usuarios",
    ]);
  });

  it("marca la página actual, también en sus subpáginas", () => {
    marco({ ruta: "/gastos/nuevo" });
    expect(within(barraLateral()).getByRole("link", { name: "Gastos" })).toHaveAttribute("aria-current", "page");
    expect(within(barraLateral()).getByRole("link", { name: "Viajes" })).not.toHaveAttribute("aria-current");
  });

  it("las pantallas actuales se enlazan con su dirección completa", () => {
    marco({ permiso: "admin" });
    expect(within(barraLateral()).getByRole("link", { name: "Usuarios" })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8000/admin/usuarios",
    );
  });

  it("dice el permiso y, solo cuando corresponde, «Entorno de demostración»", () => {
    const { unmount } = marco({ permiso: "admin", entornoDemo: true });
    expect(screen.getAllByText("Administración").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Entorno de demostración").length).toBeGreaterThan(0);
    unmount();
    marco({ permiso: "gestor", entornoDemo: false });
    expect(screen.getAllByText("Gestión de proyectos").length).toBeGreaterThan(0);
    expect(screen.queryByText("Entorno de demostración")).not.toBeInTheDocument();
  });

  it("en celular la barra se pliega tras el botón «Menú», que se abre y se cierra con teclado", async () => {
    const usuario = userEvent.setup();
    marco({ permiso: "admin" });
    const boton = screen.getByRole("button", { name: "Menú" });
    expect(boton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "Menú" })).not.toBeInTheDocument();

    await usuario.click(boton);
    expect(boton).toHaveAttribute("aria-expanded", "true");
    const panel = screen.getByRole("navigation", { name: "Menú" });
    expect(within(panel).getByRole("link", { name: "Usuarios" })).toBeInTheDocument();

    await usuario.keyboard("{Escape}");
    expect(boton).toHaveAttribute("aria-expanded", "false");
    expect(boton).toHaveFocus();
  });

  it("la barra inferior del celular solo lleva los atajos", () => {
    marco({ permiso: "colaborador" });
    const atajos = screen.getByRole("navigation", { name: "Atajos" });
    expect(within(atajos).getAllByRole("link").map((a) => a.textContent)).toEqual(["Cotizar", "Viajes", "Gastos"]);
  });
});
