import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { resumenDePrueba } from "@/test/fabricas";
import type { AdministracionRepository } from "../domain/administracion";
import { crearAdministracionMemoria } from "../infrastructure/administracion-memoria";
import { PantallaResumen } from "./pantalla-resumen";

function conResumen(datos = resumenDePrueba()) {
  return renderizarConFuente(<PantallaResumen />, { administracion: crearAdministracionMemoria({ resumen: datos }) });
}

describe("Panel de administración", () => {
  it("mientras carga muestra un esqueleto que lo anuncia", () => {
    conResumen();
    expect(screen.getByText("Cargando el resumen…").closest('[role="status"]')).not.toBeNull();
  });

  it("muestra los indicadores con su moneda", async () => {
    conResumen();
    const indicadores = await screen.findByRole("group", { name: "Indicadores del presupuesto" });
    expect(within(indicadores).getByText("Presupuesto aprobado")).toBeInTheDocument();
    expect(within(indicadores).getByText("USD 15.000,00")).toBeInTheDocument();
    expect(within(indicadores).getByText("USD 10.799,50")).toBeInTheDocument();
    expect(within(indicadores).getByText("28 % del aprobado")).toBeInTheDocument();
  });

  it("la actividad reciente lleva a revisar lo que está en revisión y a ver el detalle de lo demás", async () => {
    conResumen();
    const tabla = await screen.findByRole("table", { name: "Actividad reciente" });
    const filas = within(tabla).getAllByRole("row").slice(1);
    expect(within(filas[0]!).getByText("Alex Rivera")).toBeInTheDocument();
    expect(within(filas[0]!).getByText("V-2026-0012")).toBeInTheDocument();
    expect(within(filas[0]!).getByText("USD 54,00")).toBeInTheDocument();
    expect(within(filas[0]!).getByRole("link", { name: "Revisar el gasto de Café del centro" })).toHaveAttribute(
      "href",
      "/gastos/123",
    );
    expect(within(filas[1]!).getByRole("link", { name: "Ver detalle del gasto de Hotel de ejemplo" })).toHaveAttribute(
      "href",
      "/gastos/122",
    );
  });

  it("da acceso directo a los viajes por aprobar y explica cómo se calcula el disponible", async () => {
    conResumen();
    const pendientes = await screen.findByRole("region", { name: "Viajes por aprobar" });
    expect(within(pendientes).getByRole("link", { name: /V-2026-0012/ })).toHaveAttribute("href", "/viajes/12");
    expect(screen.getByRole("link", { name: "Aprobar viajes" })).toHaveAttribute("href", "/viajes?estado=pendiente_aprobacion");
    expect(screen.getByText(/Presupuesto disponible = aprobado − gastos aprobados/)).toBeInTheDocument();
  });

  it("dice cuando los datos son de demostración", async () => {
    conResumen(resumenDePrueba({ datos_demostracion: true }));
    expect(await screen.findByText("Solo datos de demostración")).toBeInTheDocument();
  });

  it("sin actividad ni pendientes explica qué falta y qué hacer", async () => {
    conResumen(resumenDePrueba({ actividad: [], pendientes: [], revision: [], viajes_por_aprobar: 0, gastos_en_revision: 0 }));
    expect(await screen.findByRole("heading", { name: "Todavía no hay gastos" })).toBeInTheDocument();
    expect(screen.getByText("No hay viajes esperando aprobación.")).toBeInTheDocument();
    expect(screen.getByText("No hay gastos esperando revisión.")).toBeInTheDocument();
  });

  it("si falla dice qué pasó y permite reintentar", async () => {
    const usuario = userEvent.setup();
    const resumen = vi
      .fn<AdministracionRepository["resumen"]>()
      .mockRejectedValueOnce(new ErrorDeAplicacion("servidor", { idPeticion: "r9" }))
      .mockResolvedValueOnce(resumenDePrueba());
    renderizarConFuente(<PantallaResumen />, { administracion: { ...crearAdministracionMemoria({}), resumen } });
    expect(await screen.findByText("No se pudo cargar la información")).toBeInTheDocument();
    expect(screen.getByText("Referencia: r9")).toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("table", { name: "Actividad reciente" })).toBeInTheDocument();
  });

  it("para otro permiso explica que la página es de administración", async () => {
    renderizarConFuente(<PantallaResumen />, { administracion: crearAdministracionMemoria({ resumen: null }) });
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a mis viajes" })).toHaveAttribute("href", "/viajes");
  });
});
