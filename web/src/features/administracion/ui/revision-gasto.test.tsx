import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { GastoDetalle, GastosRepository } from "@/features/gastos/domain/gastos";
import { crearGastosMemoria } from "@/features/gastos/infrastructure/gastos-memoria";
import { PantallaDetalleGasto } from "@/features/gastos/ui/pantalla-detalle-gasto";
import { ErrorDeAplicacion } from "@/shared/domain/errores";
import { renderizarConFuente } from "@/test/renderizar";
import { gastoDePrueba, resumenDePrueba } from "@/test/fabricas";
import type { AdministracionRepository } from "../domain/administracion";
import { crearAdministracionMemoria } from "../infrastructure/administracion-memoria";

const navegacion = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navegacion, usePathname: () => "/gastos/123" }));

const EN_REVISION = gastoDePrueba({
  id: 123,
  comercio: "Café del centro",
  version: 3,
  alertas: ["El total no cuadra con el subtotal y el impuesto."],
  documento_id: 55,
});

function montar({
  gastos = [EN_REVISION, gastoDePrueba({ id: 124, comercio: "Taxi aeropuerto", creado: "2026-11-11T04:00:00Z" })],
  revisar,
  permiso = "admin",
}: {
  gastos?: GastoDetalle[];
  revisar?: AdministracionRepository["revisarGasto"];
  permiso?: "admin" | "colaborador";
} = {}) {
  navegacion.push.mockClear();
  const repoGastos: GastosRepository = { ...crearGastosMemoria({ gastos }), urlOriginal: (id) => `/api/v1/documentos/${id}/contenido` };
  const obtener = vi.spyOn(repoGastos, "obtener");
  const administracion = {
    ...crearAdministracionMemoria({ resumen: resumenDePrueba() }),
    revisarGasto: vi.fn<AdministracionRepository["revisarGasto"]>(
      revisar ?? (async (_id, r) => ({ ...EN_REVISION, estado: r.accion === "aprobar" ? "aprobado" : "rechazado", estado_texto: "Hecho", version: 4 })),
    ),
  };
  renderizarConFuente(<PantallaDetalleGasto id={123} />, { gastos: repoGastos, administracion, permiso });
  return { revisar: administracion.revisarGasto, obtener };
}

describe("Revisar un gasto", () => {
  it("muestra el recibo junto a lo leído y por qué va a revisión", async () => {
    montar();
    expect(await screen.findByRole("heading", { level: 1, name: "Revisar: Café del centro" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Recibo original de Café del centro" })).toHaveAttribute(
      "src",
      "/api/v1/documentos/55/contenido",
    );
    const motivos = screen.getByRole("region", { name: "Por qué va a revisión" });
    expect(within(motivos).getByText("El total no cuadra con el subtotal y el impuesto.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Lo que leímos del recibo" })).toHaveTextContent("USD 54,00");
  });

  it("aprobar manda la versión vista y pasa al siguiente gasto en revisión", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "aprobar" });
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/Gasto aprobado/)).toBeInTheDocument();
    expect(navegacion.push).toHaveBeenCalledWith("/gastos/124");
  });

  it("si no quedan pendientes lo dice y se queda en el gasto", async () => {
    const usuario = userEvent.setup();
    montar({ gastos: [EN_REVISION] });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(await within(screen.getByRole("status", { name: "Avisos" })).findByText(/No quedan gastos en revisión/)).toBeInTheDocument();
    expect(navegacion.push).not.toHaveBeenCalled();
  });

  it("rechazar exige un motivo de 5 o más caracteres", async () => {
    const usuario = userEvent.setup();
    const { revisar } = montar();
    await usuario.click(await screen.findByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog", { name: "Rechazar el gasto de Café del centro" });
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar gasto" }));
    expect(within(dialogo).getByText(/al menos 5 caracteres/)).toBeInTheDocument();
    expect(revisar).not.toHaveBeenCalled();
    await usuario.type(within(dialogo).getByLabelText("Motivo del rechazo"), "Es un gasto personal");
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar gasto" }));
    expect(revisar).toHaveBeenCalledWith(123, { version: 3, accion: "rechazar", motivo: "Es un gasto personal" });
  });

  it("si otra persona lo cambió, avisa, recarga lo último y conserva lo escrito", async () => {
    const usuario = userEvent.setup();
    const { obtener } = montar({
      revisar: async () => {
        throw new ErrorDeAplicacion("cambio_ajeno");
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog");
    await usuario.type(within(dialogo).getByLabelText("Motivo del rechazo"), "Es un gasto personal");
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar gasto" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Otra persona lo cambió");
    expect(obtener.mock.calls.length).toBeGreaterThan(1);
    await usuario.click(screen.getByRole("button", { name: "Rechazar" }));
    expect(screen.getByLabelText("Motivo del rechazo")).toHaveValue("Es un gasto personal");
  });

  it("si el gasto es suyo, explica que lo revisa otra persona", async () => {
    const usuario = userEvent.setup();
    montar({
      revisar: async () => {
        throw new ErrorDeAplicacion("prohibido");
      },
    });
    await usuario.click(await screen.findByRole("button", { name: "Aprobar gasto" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("lo revisa otra persona de administración");
  });

  it("quien no es de administración ve su gasto sin botones de revisión", async () => {
    montar({ permiso: "colaborador" });
    expect(await screen.findByRole("heading", { level: 1, name: "Café del centro" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprobar gasto" })).not.toBeInTheDocument();
  });
});
