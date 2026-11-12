import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { crearGastosMemoria } from "@/features/gastos/infrastructure/gastos-memoria";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { gastoDePrueba, viajeDePrueba } from "@/test/fabricas";
import type { ViajeDetalle, ViajesRepository } from "../domain/viajes";
import { PantallaDetalleViaje } from "./pantalla-detalle-viaje";

function viaje(datos: Partial<ViajeDetalle> = {}): ViajeDetalle {
  return {
    ...viajeDePrueba({ id: 7, codigo: "V-2026-0007", propio: true }),
    presupuesto_detalle: [
      { concepto: "Precio del vuelo", valor: "410.00", grupo: "vuelo" },
      { concepto: "Hotel (3 noches)", valor: "390.00", grupo: "hotel" },
    ],
    motivo: null,
    aprobado_en: "2026-11-10T12:00:00Z",
    ...datos,
  };
}

function montar(detalle: ViajeDetalle | ErrorDeAplicacion, permiso: "admin" | "gestor" | "colaborador" = "colaborador") {
  const viajes: ViajesRepository = {
    listar: () => Promise.resolve({ items: [], siguiente: null }),
    obtener: () => (detalle instanceof ErrorDeAplicacion ? Promise.reject(detalle) : Promise.resolve(detalle)),
  };
  const gastos = crearGastosMemoria({ gastos: [gastoDePrueba({ id: 55, comercio: "Café del centro", viaje: { id: 7, codigo: "V-2026-0007" } })] });
  renderizarConFuente(<PantallaDetalleViaje id={7} />, { viajes, gastos, permiso });
}

describe("Detalle del viaje", () => {
  it("dice dónde estás, el estado y el desglose del presupuesto con su moneda", async () => {
    montar(viaje());
    expect(await screen.findByRole("heading", { level: 1, name: "V-2026-0007" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Migas de pan" })).toHaveTextContent("Viajes");
    const desglose = screen.getByRole("table", { name: "Desglose del presupuesto" });
    expect(within(desglose).getByText("Precio del vuelo")).toBeInTheDocument();
    expect(within(desglose).getByText("USD 390,00")).toBeInTheDocument();
  });

  it("aprobado y propio: el siguiente paso es cargar un recibo de ese viaje", async () => {
    montar(viaje());
    expect(await screen.findByRole("link", { name: "Cargar recibo" })).toHaveAttribute("href", "/gastos/nuevo?viaje=7");
  });

  it("muestra los gastos del viaje con su estado", async () => {
    montar(viaje());
    const gastos = await screen.findByRole("list", { name: "Gastos del viaje" });
    expect(within(gastos).getByRole("link", { name: "Café del centro" })).toHaveAttribute("href", "/gastos/55");
    expect(within(gastos).getByText("En revisión")).toBeInTheDocument();
  });

  it("pendiente: explica que espera la aprobación de administración", async () => {
    montar(viaje({ estado: "pendiente_aprobacion", estado_texto: "Pendiente de aprobación", en_curso: false }));
    expect(await screen.findByText("Esperando la aprobación de administración.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Cargar recibo" })).not.toBeInTheDocument();
  });

  it("rechazado: muestra el motivo y ofrece cotizar de nuevo", async () => {
    montar(viaje({ estado: "rechazado", estado_texto: "Rechazado", en_curso: false, motivo: "El hotel está lejos del set" }));
    expect(await screen.findByText("El hotel está lejos del set")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cotizar de nuevo" })).toHaveAttribute("href", "/cotizar");
  });

  it("administración puede cerrar un viaje aprobado de otra persona, con confirmación", async () => {
    montar(viaje({ propio: false }), "admin");
    expect(await screen.findByRole("button", { name: "Cerrar viaje" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Cargar recibo" })).not.toBeInTheDocument();
  });

  it("si no existe o no es visible lo dice y ofrece volver", async () => {
    montar(new ErrorDeAplicacion("no_encontrado"));
    expect(await screen.findByText("No encontramos esta información")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Volver a viajes" })).toHaveAttribute("href", "/viajes");
  });
});
