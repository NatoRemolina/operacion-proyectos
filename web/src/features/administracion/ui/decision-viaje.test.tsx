import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ViajeDetalle } from "@/features/viajes/domain/viajes";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { viajeDePrueba } from "@/test/fabricas";
import type { AdministracionRepository } from "../domain/administracion";
import { crearAdministracionMemoria } from "../infrastructure/administracion-memoria";
import { DecisionViaje } from "./decision-viaje";

const PENDIENTE = viajeDePrueba({
  id: 12,
  codigo: "V-2026-0012",
  estado: "pendiente_aprobacion",
  estado_texto: "Pendiente de aprobación",
  en_curso: false,
  titular: { id: 7, codigo: "P-0007", nombre: "Alex Rivera" },
});

function detalle(datos: Partial<ViajeDetalle> = {}): ViajeDetalle {
  return { ...PENDIENTE, presupuesto_detalle: [], motivo: null, aprobado_en: null, ...datos };
}

function montar(cambiar: AdministracionRepository["cambiarEstadoViaje"], viaje = PENDIENTE, permiso: "admin" | "gestor" = "admin") {
  const administracion = { ...crearAdministracionMemoria({}), cambiarEstadoViaje: vi.fn(cambiar) };
  renderizarConFuente(<DecisionViaje viaje={viaje} />, { administracion, permiso, personaId: 1 });
  return administracion.cambiarEstadoViaje;
}

function avisos() {
  return screen.getByRole("status", { name: "Avisos" });
}

describe("Decidir un viaje pendiente", () => {
  it("administración aprueba el presupuesto y ve el aviso con lo que pasó", async () => {
    const usuario = userEvent.setup();
    const cambiar = montar(async () => ({
      viaje: detalle({ estado: "aprobado", estado_texto: "Aprobado" }),
      mensaje: "V-2026-0012: presupuesto aprobado. Precio no reconfirmado (sin clave).",
    }));
    await usuario.click(screen.getByRole("button", { name: "Aprobar presupuesto" }));
    expect(cambiar).toHaveBeenCalledWith(12, { accion: "aprobar", confirmarPrecio: false });
    expect(await within(avisos()).findByText(/presupuesto aprobado/)).toBeInTheDocument();
  });

  it("si el precio cambió, lo muestra y aprueba con «Confirmar precio y aprobar»", async () => {
    const usuario = userEvent.setup();
    const viaje = { ...PENDIENTE, precio_por_confirmar: "antes 410.00 USD, ahora 451.00 USD (+10.0%)" };
    const cambiar = montar(async () => ({ viaje: detalle({ estado: "aprobado" }), mensaje: "Aprobado." }), viaje);
    expect(screen.getByText(/antes 410.00 USD, ahora 451.00 USD/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprobar presupuesto" })).not.toBeInTheDocument();
    await usuario.click(screen.getByRole("button", { name: "Confirmar precio y aprobar" }));
    expect(cambiar).toHaveBeenCalledWith(12, { accion: "aprobar", confirmarPrecio: true });
  });

  it("si al aprobar el servidor descubre que el precio subió, ofrece confirmarlo", async () => {
    const usuario = userEvent.setup();
    const cambiar = montar(async () => {
      throw new ErrorDeAplicacion("precio_por_confirmar", {
        mensaje: "El precio del vuelo de V-2026-0012 cambió.",
        campos: { precio: "antes 410.00 USD, ahora 451.00 USD" },
      });
    });
    await usuario.click(screen.getByRole("button", { name: "Aprobar presupuesto" }));
    expect(await screen.findByText(/antes 410.00 USD, ahora 451.00 USD/)).toBeInTheDocument();
    cambiar.mockResolvedValueOnce({ viaje: detalle({ estado: "aprobado" }), mensaje: "Aprobado." });
    await usuario.click(screen.getByRole("button", { name: "Confirmar precio y aprobar" }));
    expect(cambiar).toHaveBeenLastCalledWith(12, { accion: "aprobar", confirmarPrecio: true });
  });

  it("rechazar pide confirmación con el motivo y lo valida antes de enviar", async () => {
    const usuario = userEvent.setup();
    const cambiar = montar(async () => ({ viaje: detalle({ estado: "rechazado" }), mensaje: "Rechazado." }));
    await usuario.click(screen.getByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog", { name: "Rechazar el presupuesto de V-2026-0012" });
    await usuario.type(within(dialogo).getByLabelText("Motivo del rechazo"), "no");
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar presupuesto" }));
    expect(within(dialogo).getByText(/al menos 5 caracteres/)).toBeInTheDocument();
    expect(cambiar).not.toHaveBeenCalled();

    await usuario.type(within(dialogo).getByLabelText("Motivo del rechazo"), " conviene otra fecha");
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar presupuesto" }));
    expect(cambiar).toHaveBeenCalledWith(12, { accion: "rechazar", motivo: "no conviene otra fecha" });
  });

  it("si el viaje es propio no ofrece decidir y explica quién lo aprueba", () => {
    montar(async () => ({ viaje: detalle(), mensaje: "" }), { ...PENDIENTE, propio: true });
    expect(screen.queryByRole("button", { name: "Aprobar presupuesto" })).not.toBeInTheDocument();
    expect(screen.getByText("Es tu viaje: lo aprueba otra persona de administración.")).toBeInTheDocument();
  });

  it("el gestor no ve botones que no puede usar", () => {
    montar(async () => ({ viaje: detalle(), mensaje: "" }), PENDIENTE, "gestor");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Esperando la aprobación de administración.")).toBeInTheDocument();
  });

  it("si el servidor impide la autoaprobación lo explica sin error técnico", async () => {
    const usuario = userEvent.setup();
    montar(async () => {
      throw new ErrorDeAplicacion("autoaprobacion", {
        mensaje: "Nadie aprueba ni rechaza su propio presupuesto: debe hacerlo otra persona de administración.",
      });
    });
    await usuario.click(screen.getByRole("button", { name: "Aprobar presupuesto" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("debe hacerlo otra persona de administración");
  });

  it("el aviso del motivo corto se va mientras se escribe, sin esperar a salir del campo", async () => {
    const usuario = userEvent.setup();
    montar(async () => ({ viaje: detalle({ estado: "rechazado" }), mensaje: "Rechazado." }));
    await usuario.click(screen.getByRole("button", { name: "Rechazar" }));
    const campo = screen.getByLabelText("Motivo del rechazo");
    await usuario.type(campo, "no");
    await usuario.tab();
    expect(screen.getByText(/al menos 5 caracteres/)).toBeInTheDocument();
    await usuario.type(campo, " conviene");
    expect(campo).toHaveFocus();
    expect(screen.queryByText(/al menos 5 caracteres/)).not.toBeInTheDocument();
  });
});

