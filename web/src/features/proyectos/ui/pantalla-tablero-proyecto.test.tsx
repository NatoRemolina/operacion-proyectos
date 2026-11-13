import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Permiso } from "@/shared/domain/navegacion";
import { renderizarConFuente } from "@/test/renderizar";
import { ProyectosRepositoryProvider } from "../application/proyectos";
import type { ProyectosRepository, TableroProyecto } from "../domain/proyectos";
import { crearProyectosMemoria } from "../infrastructure/proyectos-memoria";
import { tableroDePrueba } from "../test/fabricas";
import { PantallaTableroProyecto } from "./pantalla-tablero-proyecto";

function montar({
  tablero = tableroDePrueba(),
  permiso = "admin",
  id = 1,
  conDescargas = true,
}: { tablero?: TableroProyecto; permiso?: Permiso; id?: number; conDescargas?: boolean } = {}) {
  const memoria = crearProyectosMemoria({ proyectos: [tablero.proyecto], tableros: [tablero], permiso });
  const repo: ProyectosRepository = conDescargas
    ? {
        ...memoria,
        urlCsv: (pid) => `/api/v1/proyectos/${pid}/exportar.csv`,
        urlLibroContable: (pid, { desde, hasta }) => `/api/v1/gastos/contable?desde=${desde}&hasta=${hasta}&proyecto_id=${pid}`,
      }
    : memoria;
  renderizarConFuente(
    <ProyectosRepositoryProvider repositorio={repo}>
      <PantallaTableroProyecto id={id} />
    </ProyectosRepositoryProvider>,
    { permiso },
  );
}

describe("Tablero del proyecto", () => {
  it("muestra previsto, real, diferencia y lo que espera revisión", async () => {
    montar();
    expect(await screen.findByRole("heading", { level: 1, name: "Residencial Summerlin (aéreo)" })).toBeInTheDocument();
    const indicadores = screen.getByRole("group", { name: "Cifras del proyecto" });
    expect(within(indicadores).getByText("USD 1.500,00")).toBeInTheDocument();
    expect(within(indicadores).getByText("USD 1.620,50")).toBeInTheDocument();
    const diferencia = within(indicadores).getByText(/USD 120,50/);
    // En la tarjeta la cifra va alineada como las demás; a la derecha solo en las tablas.
    expect(diferencia.parentElement).not.toHaveClass("justify-end");
    expect(within(indicadores).getByText("1")).toBeInTheDocument();
    expect(screen.getByText(/no ha llegado soporte de Hotel/)).toBeInTheDocument();
  });

  it("compara por categoría en una tabla legible además de las barras", async () => {
    montar();
    const tabla = await screen.findByRole("table", { name: "Previsto frente a real por categoría" });
    const fila = within(tabla).getByText("Vuelo").closest("tr")!;
    expect(within(fila).getByText("USD 900,00")).toBeInTheDocument();
    expect(within(fila).getByText("USD 1.000,00")).toBeInTheDocument();
    expect(within(fila).getByText(/USD 100,00/)).toBeInTheDocument();
  });

  it("enlaza sus viajes y sus gastos", async () => {
    montar();
    expect(await screen.findByRole("link", { name: "V-2026-0007" })).toHaveAttribute("href", "/viajes/7");
    const gastos = screen.getByRole("table", { name: "Gastos del proyecto" });
    expect(within(gastos).getByRole("link", { name: "Delta Air Lines" })).toHaveAttribute("href", "/gastos/41");
    expect(within(gastos).getAllByText("Alex Rivera").length).toBeGreaterThan(0);
  });

  it("descarga el CSV y el Excel contable del proyecto con el periodo elegido", async () => {
    const usuario = userEvent.setup();
    montar();
    expect(await screen.findByRole("link", { name: "Exportar CSV" })).toHaveAttribute("href", "/api/v1/proyectos/1/exportar.csv");
    const excel = screen.getByRole("link", { name: "Descargar Excel contable" });
    expect(excel).toHaveAttribute("href", "/api/v1/gastos/contable?desde=2026-11-01&hasta=2026-11-30&proyecto_id=1");
    const desde = screen.getByLabelText("Desde");
    await usuario.clear(desde);
    await usuario.type(desde, "2026-10-01");
    expect(screen.getByRole("link", { name: "Descargar Excel contable" })).toHaveAttribute(
      "href",
      "/api/v1/gastos/contable?desde=2026-10-01&hasta=2026-11-30&proyecto_id=1",
    );
  });

  it("sin descargas disponibles (modo demostración) los botones lo explican", async () => {
    montar({ conDescargas: false });
    expect(await screen.findByRole("button", { name: "Exportar CSV" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Descargar Excel contable" })).toBeDisabled();
  });

  it("administración edita el proyecto y el encabezado se actualiza", async () => {
    const usuario = userEvent.setup();
    montar();
    await screen.findByRole("heading", { level: 1, name: "Residencial Summerlin (aéreo)" });
    await usuario.click(screen.getByRole("button", { name: "Editar proyecto" }));
    const formulario = screen.getByRole("form", { name: "Editar proyecto" });
    expect(within(formulario).getByLabelText("Nombre")).toHaveValue("Residencial Summerlin (aéreo)");
    const ciudad = within(formulario).getByLabelText("Ciudad");
    await usuario.clear(ciudad);
    await usuario.type(ciudad, "Henderson");
    await usuario.click(within(formulario).getByRole("button", { name: "Guardar cambios" }));
    expect(await screen.findByText("Proyecto actualizado.")).toBeInTheDocument();
    expect(screen.getByText(/Henderson/)).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Editar proyecto" })).not.toBeInTheDocument();
  });

  it("quien gestiona ve el tablero sin poder editarlo", async () => {
    montar({ permiso: "gestor" });
    await screen.findByRole("heading", { level: 1, name: "Residencial Summerlin (aéreo)" });
    expect(screen.queryByRole("button", { name: "Editar proyecto" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Exportar CSV" })).toBeInTheDocument();
  });

  it("un proyecto ajeno o inexistente responde que no se encontró", async () => {
    montar({ id: 99 });
    expect(await screen.findByText("No encontramos esta información")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a proyectos" })).toHaveAttribute("href", "/proyectos");
  });
});
