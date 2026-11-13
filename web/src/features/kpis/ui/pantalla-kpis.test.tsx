import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderizarConFuente } from "@/test/renderizar";
import { KpisRepositoryProvider } from "../application/kpis";
import type { KpisRepository } from "../domain/kpis";
import { FICHA_EJEMPLO, RUTAS_FRECUENTES_EJEMPLO, TABLERO_EJEMPLO } from "../infrastructure/ejemplo-kpis";
import { crearKpisMemoria } from "../infrastructure/kpis-memoria";
import { PantallaFichaPersona } from "./pantalla-ficha-persona";
import { PantallaKpis } from "./pantalla-kpis";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }), usePathname: () => "/kpis" }));

const SIN = { proyecto_id: null, desde: null, hasta: null };

function montar(ui: React.ReactElement, repo: KpisRepository) {
  return renderizarConFuente(<KpisRepositoryProvider repositorio={repo}>{ui}</KpisRepositoryProvider>, { permiso: "admin" });
}

describe("Pantalla de KPIs", () => {
  it("muestra cada indicador con su valor, semáforo en texto, meta y responsable, agrupado por reto", async () => {
    montar(<PantallaKpis filtros={SIN} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO }));
    const reto1 = await screen.findByRole("heading", { name: "Reto 1: Cotización de viajes" });
    expect(reto1).toBeInTheDocument();
    const tarjeta = screen.getByRole("article", { name: "Búsquedas resueltas sin pagar otra consulta" });
    expect(within(tarjeta).getByText("72 %")).toBeInTheDocument();
    expect(within(tarjeta).getByText("En meta")).toBeInTheDocument();
    expect(within(tarjeta).getByText(/Meta ≥ 60 % · rojo si < 30 %/)).toBeInTheDocument();
    const rojo = screen.getByRole("article", { name: "Gasto aprobado sobre presupuesto aprobado" });
    expect(within(rojo).getByText("Fuera de meta")).toBeInTheDocument();
    const sinDatos = screen.getByRole("article", { name: "Gastos sin viaje" });
    expect(within(sinDatos).getAllByText("Sin datos").length).toBeGreaterThan(0);
    expect(screen.getByText("1 fuera de meta")).toBeInTheDocument();
  });

  it("un valor imposible (−28 días) sale «Fuera de rango», nunca «En meta» (M-20)", async () => {
    montar(<PantallaKpis filtros={SIN} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO }));
    const tarjeta = await screen.findByRole("article", { name: "Mediana de días del recibo a la carga" });
    expect(within(tarjeta).getByText("Fuera de rango")).toBeInTheDocument();
    expect(within(tarjeta).queryByText("En meta")).not.toBeInTheDocument();
    expect(within(tarjeta).getByText(/no es posible para el indicador/)).toBeInTheDocument();
    expect(screen.getByText("1 fuera de rango")).toBeInTheDocument();
  });

  it("la tendencia, las personas con su ficha y la ejecución por viaje", async () => {
    montar(<PantallaKpis filtros={SIN} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO }));
    expect(await screen.findByRole("region", { name: "Tendencia semanal (se desliza de lado)" })).toBeInTheDocument();
    const personas = screen.getAllByRole("link", { name: /P-0002 · Ana Piloto/ });
    expect(personas[0]).toHaveAttribute("href", "/kpis/persona/2");
    expect(screen.getByRole("link", { name: "V-2026-0007" })).toHaveAttribute("href", "/viajes/7");
  });

  it("aplica los filtros cambiando la dirección y no acepta un rango al revés", async () => {
    const usuario = userEvent.setup();
    montar(<PantallaKpis filtros={SIN} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO }));
    await screen.findByRole("heading", { name: "Reto 1: Cotización de viajes" });
    await usuario.selectOptions(screen.getByLabelText("Proyecto"), "1");
    await usuario.type(screen.getByLabelText("Desde"), "2026-11-10");
    await usuario.type(screen.getByLabelText("Hasta"), "2026-11-01");
    await usuario.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(screen.getByText("«Hasta» no puede ser antes de «Desde».")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    await usuario.clear(screen.getByLabelText("Hasta"));
    await usuario.click(screen.getByRole("button", { name: "Aplicar" }));
    expect(push).toHaveBeenCalledWith("/kpis?proyecto=1&desde=2026-11-10");
  });

  it("ofrece las descargas con los filtros cuando la fuente exporta", async () => {
    const repo: KpisRepository = { ...crearKpisMemoria({ tablero: TABLERO_EJEMPLO }), urlExportar: (que) => `/api/v1/kpis/exportar.csv?que=${que}` };
    montar(<PantallaKpis filtros={SIN} />, repo);
    expect(await screen.findByRole("link", { name: "Personas" })).toHaveAttribute("href", "/api/v1/kpis/exportar.csv?que=personas");
  });

  it("sin permiso lo dice, sin mostrar datos", async () => {
    montar(<PantallaKpis filtros={SIN} />, crearKpisMemoria({ tablero: null }));
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Reto 1/ })).not.toBeInTheDocument();
  });
});

describe("Ficha de una persona", () => {
  it("muestra sus totales, sus indicadores, sus viajes y su línea de tiempo", async () => {
    montar(<PantallaFichaPersona id={2} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO, fichas: [FICHA_EJEMPLO] }));
    expect(await screen.findByRole("heading", { level: 1, name: "P-0002 · Ana Piloto" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Línea de tiempo" })).toBeInTheDocument();
    expect(screen.getByText("presupuesto aprobado")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "V-2026-0007" })).toHaveAttribute("href", "/viajes/7");
  });

  it("una persona que no existe lo dice", async () => {
    montar(<PantallaFichaPersona id={99} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO, fichas: [FICHA_EJEMPLO] }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("Rutas frecuentes y precios", () => {
  it("muestra cada ruta con la mediana por anticipación, la prima, aerolínea o agencia, la tendencia y la señal", async () => {
    montar(<PantallaKpis filtros={SIN} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO }));
    const seccion = await screen.findByRole("region", { name: "Rutas frecuentes y precios" });
    expect(await within(seccion).findByText("Cifras demostrativas")).toBeInTheDocument();
    expect(within(seccion).getAllByText("MIA → LAS").length).toBeGreaterThan(0);
    expect(within(seccion).getAllByText(/aerolínea .*13.* más barata/).length).toBeGreaterThan(0);
    expect(within(seccion).getAllByText("sube 6,4 %").length).toBeGreaterThan(0);
    expect(within(seccion).getAllByText("Dentro del rango").length).toBeGreaterThan(0);
    expect(within(seccion).getAllByText("Por encima del rango").length).toBeGreaterThan(0);
    expect(within(seccion).getByRole("region", { name: "Exactitud del precio esperado" })).toBeInTheDocument();
  });

  it("sin decisiones con precio esperado dice «sin datos todavía»", async () => {
    const vacio = {
      ...RUTAS_FRECUENTES_EJEMPLO,
      rutas: [],
      exactitud: { filas: 0, mae: null, mape: null, mensaje: "sin datos todavía", por_ruta: [], por_mes: [], contra_pagado: null },
    };
    montar(<PantallaKpis filtros={SIN} />, crearKpisMemoria({ tablero: TABLERO_EJEMPLO, rutas: vacio }));
    expect(await screen.findByText("sin datos todavía")).toBeInTheDocument();
    expect(screen.getByText(/Todavía no hay cotizaciones/)).toBeInTheDocument();
  });
});
