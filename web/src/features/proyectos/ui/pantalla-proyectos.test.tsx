import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Permiso } from "@/shared/domain/navegacion";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { ProyectosRepositoryProvider } from "../application/proyectos";
import type { ProyectoResumen, ProyectosRepository } from "../domain/proyectos";
import { crearProyectosMemoria } from "../infrastructure/proyectos-memoria";
import { proyectoDePrueba } from "../test/fabricas";
import { PantallaProyectos } from "./pantalla-proyectos";

function montar({
  proyectos = [proyectoDePrueba(), proyectoDePrueba({ id: 2, nombre: "Apartamentos Alfama (aéreo)", ciudad: "Lisboa", diferencia_usd: "-50.00" })],
  permiso = "admin",
  repositorio,
}: { proyectos?: ProyectoResumen[]; permiso?: Permiso; repositorio?: ProyectosRepository } = {}) {
  const repo = repositorio ?? crearProyectosMemoria({ proyectos, permiso });
  renderizarConFuente(
    <ProyectosRepositoryProvider repositorio={repo}>
      <PantallaProyectos />
    </ProyectosRepositoryProvider>,
    { permiso },
  );
  return repo;
}

describe("Proyectos", () => {
  it("lista cada proyecto con previsto, real y diferencia, y enlaza a su tablero", async () => {
    montar();
    const lista = await screen.findByRole("table", { name: "Proyectos" });
    const fila = within(lista).getByRole("link", { name: "Residencial Summerlin (aéreo)" }).closest("tr")!;
    expect(within(lista).getByRole("link", { name: "Residencial Summerlin (aéreo)" })).toHaveAttribute("href", "/proyectos/1");
    expect(within(fila).getByText("USD 1.500,00")).toBeInTheDocument();
    expect(within(fila).getByText("USD 1.620,50")).toBeInTheDocument();
    expect(within(fila).getByText(/USD 120,50/)).toBeInTheDocument();
    expect(within(fila).getByText(/sobre lo previsto/)).toBeInTheDocument();
  });

  it("administración crea un proyecto y aparece en la lista", async () => {
    const usuario = userEvent.setup();
    montar();
    await screen.findByRole("table", { name: "Proyectos" });
    await usuario.click(screen.getByRole("button", { name: "Nuevo proyecto" }));
    const formulario = screen.getByRole("form", { name: "Nuevo proyecto" });
    await usuario.type(within(formulario).getByLabelText("Nombre"), "Torre Norte (aéreo)");
    await usuario.type(within(formulario).getByLabelText("Ciudad"), "Denver");
    await usuario.type(within(formulario).getByLabelText("Inicio"), "2026-12-15");
    await usuario.type(within(formulario).getByLabelText("Fin"), "2026-12-18");
    await usuario.click(within(formulario).getByRole("button", { name: "Crear proyecto" }));
    const lista = screen.getByRole("table", { name: "Proyectos" });
    expect(await within(lista).findByRole("link", { name: "Torre Norte (aéreo)" })).toHaveAttribute("href", "/proyectos/3");
    expect(screen.getByText("Proyecto «Torre Norte (aéreo)» creado.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Nuevo proyecto" })).not.toBeInTheDocument();
  });

  it("un dato inválido se señala en su campo y no se envía", async () => {
    const usuario = userEvent.setup();
    const repo = montar();
    await screen.findByRole("table", { name: "Proyectos" });
    await usuario.click(screen.getByRole("button", { name: "Nuevo proyecto" }));
    const formulario = screen.getByRole("form", { name: "Nuevo proyecto" });
    await usuario.type(within(formulario).getByLabelText("Nombre"), "Torre Sur");
    await usuario.type(within(formulario).getByLabelText("Inicio"), "2026-12-15");
    await usuario.type(within(formulario).getByLabelText("Fin"), "2026-12-01");
    await usuario.click(within(formulario).getByRole("button", { name: "Crear proyecto" }));
    expect(within(formulario).getByLabelText("Fin")).toHaveAttribute("aria-invalid", "true");
    expect(within(formulario).getByText("La fecha final no puede ser anterior a la inicial.")).toBeInTheDocument();
    expect((await repo.listar({})).items).toHaveLength(2);
  });

  it("el error de un campo que devuelve el servidor se muestra junto al campo", async () => {
    const usuario = userEvent.setup();
    const base = crearProyectosMemoria({ proyectos: [proyectoDePrueba()], permiso: "admin" });
    montar({
      repositorio: {
        ...base,
        crear: () => Promise.reject(new ErrorDeAplicacion("validacion", { campos: { moneda: "La moneda no se reconoce." } })),
      },
    });
    await screen.findByRole("table", { name: "Proyectos" });
    await usuario.click(screen.getByRole("button", { name: "Nuevo proyecto" }));
    const formulario = screen.getByRole("form", { name: "Nuevo proyecto" });
    await usuario.type(within(formulario).getByLabelText("Nombre"), "Torre Sur");
    await usuario.type(within(formulario).getByLabelText("Inicio"), "2026-12-15");
    await usuario.type(within(formulario).getByLabelText("Fin"), "2026-12-18");
    await usuario.click(within(formulario).getByRole("button", { name: "Crear proyecto" }));
    expect(await within(formulario).findByText("La moneda no se reconoce.")).toBeInTheDocument();
    expect(within(formulario).getByLabelText("Moneda")).toHaveAttribute("aria-invalid", "true");
  });

  it("quien gestiona ve sus proyectos sin el botón de crear", async () => {
    montar({ permiso: "gestor", proyectos: [proyectoDePrueba()] });
    const lista = await screen.findByRole("table", { name: "Proyectos" });
    expect(within(lista).getByRole("link", { name: "Residencial Summerlin (aéreo)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nuevo proyecto" })).not.toBeInTheDocument();
  });

  it("sin proyectos lo dice", async () => {
    montar({ proyectos: [] });
    expect(await screen.findByRole("heading", { name: "Aún no hay proyectos" })).toBeInTheDocument();
  });

  it("colaboración no tiene proyectos que ver: lo dice sin romperse", async () => {
    montar({ permiso: "colaborador" });
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
  });
});
