import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { crearAdministracionMemoria } from "@/features/administracion/infrastructure/administracion-memoria";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import type { CatalogoReglas, Regla } from "../domain/reglas";
import { PantallaReglas } from "./pantalla-reglas";

const TOLERANCIA: Regla = {
  id: 26, ambito: "supuesto", entidad: "", tarifa: "", clave: "tolerancia_presupuesto", valor: "0.1", numerica: true,
  nota: "Holgura del presupuesto del viaje.", fuente: "Supuesto de la empresa", confianza: "supuesto", verificado: "2026-11-11",
};
const EQUIPAJE: Regla = {
  id: 3, ambito: "aerolinea", entidad: "United", tarifa: "basica", clave: "equipaje_mano", valor: "no", numerica: false,
  nota: "En rutas nacionales solo artículo personal.", fuente: "https://www.united.com/basic-economy", confianza: "oficial",
  verificado: "2026-11-11",
};
const CUENTA: Regla = { ...TOLERANCIA, id: 90, clave: "cuenta_contable_hotel", valor: "5135", nota: "Cuenta de hoteles." };

const CATALOGO: CatalogoReglas = {
  grupos: [
    { clave: "aerolinea", titulo: "Aerolíneas", reglas: [EQUIPAJE] },
    { clave: "supuesto", titulo: "Supuestos", reglas: [TOLERANCIA] },
    { clave: "cuenta_contable", titulo: "Cuentas contables", reglas: [CUENTA] },
  ],
  membresias: [
    { id: 1, titular: "Alex Rivera", de_empresa: false, programa: "AAdvantage", entidad: "American", estatus: "Gold", ejemplo: true },
    { id: 3, titular: "Empresa", de_empresa: true, programa: "AAdvantage Business", entidad: "American", estatus: "", ejemplo: false },
  ],
};

function montar({ catalogo = CATALOGO, editar }: { catalogo?: CatalogoReglas | null; editar?: (id: number, valor: string) => Promise<Regla> } = {}) {
  const memoria = crearAdministracionMemoria({ reglas: catalogo });
  const administracion = { ...memoria, editarRegla: vi.fn(editar ?? memoria.editarRegla) };
  renderizarConFuente(<PantallaReglas />, { administracion, permiso: "admin" });
  return { editar: administracion.editarRegla };
}

describe("Reglas y supuestos", () => {
  it("muestra las reglas agrupadas por ámbito con su valor, nota, fuente y confianza", async () => {
    montar();
    expect(await screen.findByRole("heading", { level: 1, name: "Reglas y supuestos" })).toBeInTheDocument();
    const aerolineas = await screen.findByRole("region", { name: /Aerolíneas/ });
    expect(within(aerolineas).getByText("equipaje_mano")).toBeInTheDocument();
    expect(within(aerolineas).getByLabelText("Valor de equipaje_mano")).toHaveValue("no");
    expect(within(aerolineas).getByText("En rutas nacionales solo artículo personal.")).toBeInTheDocument();
    expect(within(aerolineas).getByRole("link", { name: /Fuente/ })).toHaveAttribute("href", "https://www.united.com/basic-economy");
    expect(within(aerolineas).getByText("oficial")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /Cuentas contables/ })).toHaveTextContent("cuenta_contable_hotel");
  });

  it("una fuente que no es una dirección se muestra como texto", async () => {
    montar();
    const supuestos = await screen.findByRole("region", { name: /Supuestos/ });
    expect(within(supuestos).getByText(/Supuesto de la empresa/)).toBeInTheDocument();
    expect(within(supuestos).queryByRole("link", { name: /Fuente/ })).not.toBeInTheDocument();
  });

  it("guardar una regla numérica con coma decimal la envía con punto y lo confirma", async () => {
    const usuario = userEvent.setup();
    const { editar } = montar();
    const campo = await screen.findByLabelText("Valor de tolerancia_presupuesto");
    await usuario.clear(campo);
    await usuario.type(campo, "0,25");
    await usuario.click(screen.getByRole("button", { name: "Guardar tolerancia_presupuesto" }));
    expect(editar).toHaveBeenCalledWith(26, "0.25");
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText("Regla guardada: tolerancia_presupuesto.")).toBeInTheDocument();
    expect(screen.getByLabelText("Valor de tolerancia_presupuesto")).toHaveValue("0.25");
  });

  it("una regla numérica no acepta texto y no se envía", async () => {
    const usuario = userEvent.setup();
    const { editar } = montar();
    const campo = await screen.findByLabelText("Valor de tolerancia_presupuesto");
    await usuario.clear(campo);
    await usuario.type(campo, "80 USD");
    await usuario.click(screen.getByRole("button", { name: "Guardar tolerancia_presupuesto" }));
    expect(campo).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/no es un número válido para tolerancia_presupuesto/)).toBeInTheDocument();
    expect(editar).not.toHaveBeenCalled();
  });

  it("una regla de texto guarda el texto", async () => {
    const usuario = userEvent.setup();
    const { editar } = montar();
    const campo = await screen.findByLabelText("Valor de equipaje_mano");
    await usuario.clear(campo);
    await usuario.type(campo, "sí, en transatlánticas");
    await usuario.click(screen.getByRole("button", { name: "Guardar equipaje_mano" }));
    expect(editar).toHaveBeenCalledWith(3, "sí, en transatlánticas");
  });

  it("si el servidor rechaza el valor, muestra su explicación junto al campo", async () => {
    const usuario = userEvent.setup();
    montar({
      editar: async () => {
        throw new ErrorDeAplicacion("validacion", { campos: { valor: "«0.1x» no es un número válido para tolerancia_presupuesto. No se guardó." } });
      },
    });
    const campo = await screen.findByLabelText("Valor de equipaje_mano");
    await usuario.type(campo, " más");
    await usuario.click(screen.getByRole("button", { name: "Guardar equipaje_mano" }));
    expect(await screen.findByText(/«0.1x» no es un número válido/)).toBeInTheDocument();
  });

  it("sin cambios no envía nada", async () => {
    const usuario = userEvent.setup();
    const { editar } = montar();
    await usuario.click(await screen.findByRole("button", { name: "Guardar equipaje_mano" }));
    expect(editar).not.toHaveBeenCalled();
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/Sin cambios/)).toBeInTheDocument();
  });

  it("buscar deja solo las reglas que coinciden", async () => {
    const usuario = userEvent.setup();
    montar();
    await screen.findByRole("region", { name: /Aerolíneas/ });
    await usuario.type(screen.getByLabelText("Buscar una regla"), "equipaje");
    expect(screen.getByText("equipaje_mano")).toBeInTheDocument();
    expect(screen.queryByText("tolerancia_presupuesto")).not.toBeInTheDocument();
    await usuario.clear(screen.getByLabelText("Buscar una regla"));
    await usuario.type(screen.getByLabelText("Buscar una regla"), "zzz");
    expect(screen.getByText("Ninguna regla coincide con la búsqueda.")).toBeInTheDocument();
  });

  it("las membresías se ven en solo lectura con el dato de ejemplo", async () => {
    montar();
    const membresias = await screen.findByRole("region", { name: "Membresías de fidelización" });
    expect(within(membresias).getByText("Alex Rivera")).toBeInTheDocument();
    expect(within(membresias).getByText("Dato de ejemplo")).toBeInTheDocument();
    expect(within(membresias).getByText("Empresa")).toBeInTheDocument();
    expect(within(membresias).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("las migas dicen que está en Administración", async () => {
    montar();
    const migas = within(await screen.findByRole("navigation", { name: "Migas de pan" }));
    expect(migas.getByText("Administración")).toBeInTheDocument();
    expect(migas.getByText("Reglas y supuestos")).toHaveAttribute("aria-current", "page");
  });

  it("quien no es de administración no la ve", async () => {
    montar({ catalogo: null });
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
  });
});
