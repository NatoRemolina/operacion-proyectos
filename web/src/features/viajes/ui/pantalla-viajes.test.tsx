import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { crearAdministracionMemoria } from "@/features/administracion/infrastructure/administracion-memoria";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { resumenDePrueba, viajeDePrueba } from "@/test/fabricas";
import type { ViajeResumen, ViajesRepository } from "../domain/viajes";
import { crearViajesMemoria } from "../infrastructure/viajes-memoria";
import { PantallaViajes } from "./pantalla-viajes";

const PENDIENTE = viajeDePrueba({
  id: 12,
  codigo: "V-2026-0012",
  estado: "pendiente_aprobacion",
  estado_texto: "Pendiente de aprobación",
  en_curso: false,
  titular: { id: 7, codigo: "P-0007", nombre: "Alex Rivera" },
});
const APROBADO = viajeDePrueba({ id: 9, codigo: "V-2026-0009", titular: { id: 7, codigo: "P-0007", nombre: "Alex Rivera" } });

function montar({ viajes = [PENDIENTE, APROBADO], permiso = "admin", estado }: {
  viajes?: ViajeResumen[];
  permiso?: "admin" | "gestor" | "colaborador";
  estado?: "pendiente_aprobacion";
} = {}) {
  const compartidos = [...viajes];
  renderizarConFuente(<PantallaViajes estado={estado} />, {
    viajes: crearViajesMemoria({ viajes: compartidos }),
    administracion: crearAdministracionMemoria({ resumen: resumenDePrueba(), viajes: compartidos }),
    permiso,
  });
}

describe("Viajes", () => {
  it("mientras carga, un esqueleto lo anuncia", () => {
    montar();
    expect(screen.getByText("Cargando los viajes…").closest('[role="status"]')).not.toBeNull();
  });

  it("sin viajes invita a cotizar el primero", async () => {
    montar({ viajes: [], permiso: "colaborador" });
    expect(await screen.findByRole("heading", { name: "Aún no tienes viajes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cotizar mi primer viaje" })).toHaveAttribute("href", "/cotizar");
  });

  it("si falla la carga dice qué pasó y permite reintentar", async () => {
    const viajes: ViajesRepository = {
      listar: () => Promise.reject(new ErrorDeAplicacion("red")),
      obtener: () => Promise.reject(new ErrorDeAplicacion("red")),
    };
    renderizarConFuente(<PantallaViajes />, { viajes, permiso: "colaborador" });
    expect(await screen.findByText("No hubo conexión con el servidor.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });

  it("administración ve primero los viajes por aprobar y al aprobar uno sale de la lista", async () => {
    const usuario = userEvent.setup();
    montar();
    const porAprobar = await screen.findByRole("region", { name: "Por aprobar" });
    expect(await within(porAprobar).findByRole("link", { name: "V-2026-0012" })).toHaveAttribute("href", "/viajes/12");
    expect(within(porAprobar).getByText("Alex Rivera")).toBeInTheDocument();
    await usuario.click(within(porAprobar).getByRole("button", { name: "Aprobar presupuesto" }));
    expect(await screen.findByText("No hay viajes esperando aprobación.")).toBeInTheDocument();
    expect(within(screen.getByRole("status", { name: "Avisos" })).getByText("V-2026-0012: presupuesto aprobado.")).toBeInTheDocument();
  });

  it("el colaborador ve sus viajes sin la sección de aprobación y cada viaje lleva a su detalle", async () => {
    montar({ permiso: "colaborador" });
    const lista = await screen.findByRole("list", { name: "Viajes" });
    expect(within(lista).getByRole("link", { name: "V-2026-0009" })).toHaveAttribute("href", "/viajes/9");
    expect(screen.queryByRole("region", { name: "Por aprobar" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Mis viajes" })).toBeInTheDocument();
  });

  it("se puede filtrar por estado y el filtro activo se marca", async () => {
    montar({ permiso: "gestor", estado: "pendiente_aprobacion" });
    const filtros = screen.getByRole("navigation", { name: "Filtrar por estado" });
    expect(within(filtros).getByRole("link", { name: "Por aprobar" })).toHaveAttribute("aria-current", "page");
    const lista = await screen.findByRole("list", { name: "Viajes" });
    expect(within(lista).queryByText("V-2026-0009")).not.toBeInTheDocument();
    expect(within(lista).getByText("V-2026-0012")).toBeInTheDocument();
  });
});
