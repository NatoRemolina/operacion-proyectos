import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderizarConFuente } from "@/test/renderizar";
import { ComprasRepositoryProvider } from "../application/compras";
import type { ComprasRepository } from "../domain/compras";
import { crearComprasMemoria } from "../infrastructure/compras-memoria";
import { EVIDENCIA_EJEMPLO } from "@/features/cotizar/infrastructure/ejemplo-evidencia";
import { COMPRA_EJEMPLO } from "../infrastructure/ejemplo-compras";
import { PantallaCompras } from "./pantalla-compras";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/compras" }));

function montar(repo: ComprasRepository) {
  return renderizarConFuente(
    <ComprasRepositoryProvider repositorio={repo}>
      <PantallaCompras />
    </ComprasRepositoryProvider>,
    { permiso: "admin" },
  );
}

async function abrir(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.click(await screen.findByRole("button", { name: "Abrir la compra del viaje V-2026-0041" }));
  return screen.findByRole("region", { name: "Compra del viaje V-2026-0041" });
}

describe("Bandeja de compras", () => {
  it("lista las solicitudes y abre el detalle con el vuelo, el enlace oficial y los clics", async () => {
    const usuario = userEvent.setup();
    montar(crearComprasMemoria({ compras: [COMPRA_EJEMPLO], permiso: "admin" }));
    const fila = (await screen.findByRole("rowheader", { name: "V-2026-0041" })).closest("tr")!;
    expect(within(fila).getByText("Solicitud de compra enviada")).toBeInTheDocument();
    const detalle = await abrir(usuario);
    const oficial = within(detalle).getByRole("link", { name: /Comprar en la página oficial del vendedor/ });
    expect(oficial).toHaveAttribute("href", COMPRA_EJEMPLO.vuelo!.vendedor_url);
    expect(oficial).toHaveAttribute("target", "_blank");
    expect(oficial).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(detalle).getByText(/Página oficial del vendedor · www\.google\.com · Andrés Molina/)).toBeInTheDocument();
  });

  it("«Se va a comprar» espera el viaje aprobado y no comprar exige motivo", async () => {
    const usuario = userEvent.setup();
    const repo = crearComprasMemoria({ compras: [COMPRA_EJEMPLO], permiso: "admin" });
    const cambiar = vi.spyOn(repo, "cambiarEstado");
    montar(repo);
    const detalle = await abrir(usuario);
    expect(within(detalle).getByRole("button", { name: "Se va a comprar" })).toBeDisabled();
    expect(within(detalle).getByText(/no tiene el presupuesto aprobado/)).toBeInTheDocument();
    await usuario.click(within(detalle).getByRole("button", { name: "No se va a comprar" }));
    expect(within(detalle).getByText("Escribe el motivo (5 caracteres o más).")).toBeInTheDocument();
    expect(cambiar).not.toHaveBeenCalled();
    await usuario.click(within(detalle).getByRole("button", { name: "Pasar a análisis" }));
    expect(cambiar).toHaveBeenCalledWith(7, "en_analisis", 1, "");   // con la versión que se vio
    expect((await within(detalle).findAllByText("En análisis")).length).toBeGreaterThan(0);
  });

  it("nadie decide la compra de su propio viaje: el mensaje lo dice", async () => {
    const usuario = userEvent.setup();
    montar(crearComprasMemoria({ compras: [COMPRA_EJEMPLO], propias: [7], permiso: "admin" }));
    const detalle = await abrir(usuario);
    await usuario.click(within(detalle).getByRole("button", { name: "Pasar a análisis" }));
    expect(await within(detalle).findByText(/Nadie decide la compra de su propio viaje/)).toBeInTheDocument();
  });

  it("con el viaje aprobado se decide comprar y se registra el localizador, frente a lo cotizado", async () => {
    const usuario = userEvent.setup();
    const aprobada = { ...COMPRA_EJEMPLO, viaje: { ...COMPRA_EJEMPLO.viaje, estado: "aprobado" } };
    montar(crearComprasMemoria({ compras: [aprobada], permiso: "admin" }));
    const detalle = await abrir(usuario);
    await usuario.click(within(detalle).getByRole("button", { name: "Se va a comprar" }));
    const form = await within(detalle).findByRole("form", { name: "Registrar la compra" });
    await usuario.click(within(form).getByRole("button", { name: "Registrar la compra" }));
    expect(within(form).getByText("El localizador son 5 a 8 letras o números.")).toBeInTheDocument();
    await usuario.type(within(form).getByLabelText("Localizador"), "qx7z2p");
    await usuario.type(within(form).getByLabelText("Precio pagado (USD)"), "461.30");
    await usuario.type(within(form).getByLabelText("Vendedor"), "American");
    await usuario.click(within(form).getByRole("button", { name: "Registrar la compra" }));
    expect(await within(detalle).findByText("Comprada a American · QX7Z2P")).toBeInTheDocument();
    expect(within(detalle).getByText(/diferencia/)).toHaveTextContent(/3[.,]30/);
  });

  it("la ficha muestra la evidencia guardada de la decisión (pieza 5)", async () => {
    const usuario = userEvent.setup();
    montar(crearComprasMemoria({ compras: [{ ...COMPRA_EJEMPLO, evidencia: EVIDENCIA_EJEMPLO }], permiso: "admin" }));
    const detalle = await abrir(usuario);
    expect(within(detalle).getByRole("region", { name: /Evidencia guardada a las \d{2}:\d{2}/ })).toBeInTheDocument();
    expect(within(detalle).getByRole("table", { name: "Precios del seguimiento" })).toBeInTheDocument();
  });

  it("sin solicitudes lo dice", async () => {
    montar(crearComprasMemoria({ compras: [], permiso: "admin" }));
    expect(await screen.findByText("No hay solicitudes de compra")).toBeInTheDocument();
  });
});

describe("Compras en memoria", () => {
  it("fuera de administración responde «prohibido», como la API (403)", async () => {
    const repo = crearComprasMemoria({ compras: [COMPRA_EJEMPLO], permiso: "colaborador" });
    await expect(repo.lista()).rejects.toMatchObject({ tipo: "prohibido" });
    await expect(repo.detalle(7)).rejects.toMatchObject({ tipo: "prohibido" });
    await expect(repo.cambiarEstado(7, "en_analisis", 1, "")).rejects.toMatchObject({ tipo: "prohibido" });
    await expect(repo.analizar(7)).rejects.toMatchObject({ tipo: "prohibido" });
  });

  it("la bandeja lo explica a quien no es de administración", async () => {
    montar(crearComprasMemoria({ compras: [COMPRA_EJEMPLO], permiso: "gestor" }));
    expect(await screen.findByText("Esta página no está disponible con tu permiso")).toBeInTheDocument();
  });
});
