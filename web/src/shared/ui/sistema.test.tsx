import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { AvisosProvider, useAvisos } from "./aviso-emergente";
import { DialogoConfirmacion } from "./dialogo-confirmacion";
import { EncabezadoPagina } from "./encabezado-pagina";
import { EsqueletoLista } from "./esqueleto";
import { EstadoVacio } from "./estado-vacio";
import { EtiquetaEstado } from "./etiqueta-estado";
import { formatearDinero, formatearFecha } from "./formato";
import { Indicador, Indicadores } from "./indicador";
import { Migas } from "./migas";
import { Tabla } from "./tabla";

describe("formato", () => {
  it("el dinero lleva el código de la moneda delante", () => {
    expect(formatearDinero("1672.00", "USD")).toBe("USD 1.672,00");
  });

  it("las fechas se leen como «9 dic 2026»", () => {
    expect(formatearFecha("2026-12-09")).toBe("9 dic 2026");
  });
});

describe("Indicadores", () => {
  it("cada tarjeta dice qué mide, la cifra y su contexto", () => {
    render(
      <Indicadores etiqueta="Indicadores del mes">
        <Indicador etiqueta="Presupuesto aprobado" cifra="USD 15.000,00" pie="En los proyectos activos" />
      </Indicadores>,
    );
    const lista = screen.getByRole("group", { name: "Indicadores del mes" });
    expect(within(lista).getByText("Presupuesto aprobado")).toBeInTheDocument();
    expect(within(lista).getByText("USD 15.000,00")).toBeInTheDocument();
  });
});

interface Fila {
  id: number;
  comercio: string;
  importe: string;
}

const FILAS: Fila[] = [
  { id: 1, comercio: "Café del centro", importe: "USD 54,00" },
  { id: 2, comercio: "Hotel de ejemplo", importe: "USD 780,00" },
];

function tabla(acciones = false) {
  return render(
    <Tabla
      titulo="Actividad reciente"
      filas={FILAS}
      claveFila={(f) => f.id}
      hrefFila={(f) => `/gastos/${f.id}`}
      columnas={[
        { clave: "comercio", encabezado: "Comercio", celda: (f) => f.comercio, principal: true },
        { clave: "importe", encabezado: "Importe", celda: (f) => f.importe, alinear: "fin" },
      ]}
      acciones={acciones ? (f) => <button type="button">Revisar {f.comercio}</button> : undefined}
    />,
  );
}

describe("Tabla", () => {
  it("tiene título y encabezados de columna", () => {
    tabla();
    const t = screen.getByRole("table", { name: "Actividad reciente" });
    expect(within(t).getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["Comercio", "Importe"]);
  });

  it("la columna principal lleva a la fila y los importes se alinean a la derecha", () => {
    tabla();
    const t = screen.getByRole("table", { name: "Actividad reciente" });
    expect(within(t).getByRole("link", { name: "Café del centro" })).toHaveAttribute("href", "/gastos/1");
    expect(within(t).getByText("USD 780,00").closest("td")).toHaveClass("text-right");
  });

  it("en celular cada fila es una tarjeta con los mismos datos y acciones", () => {
    tabla(true);
    const tarjetas = screen.getByRole("list", { name: "Actividad reciente" });
    const primera = within(tarjetas).getAllByRole("listitem")[0]!;
    expect(within(primera).getByRole("link", { name: "Café del centro" })).toHaveAttribute("href", "/gastos/1");
    expect(within(primera).getByText("Importe")).toBeInTheDocument();
    expect(within(primera).getByRole("button", { name: "Revisar Café del centro" })).toBeInTheDocument();
  });
});

describe("Tabla de dos columnas (concepto e importe)", () => {
  it("en celular es una lista limpia: concepto a la izquierda, importe a la derecha, sin repetir la etiqueta", () => {
    render(
      <Tabla
        titulo="Desglose"
        filas={[{ id: 1, concepto: "Hotel", valor: "USD 390,00" }]}
        claveFila={(f) => f.id}
        columnas={[
          { clave: "concepto", encabezado: "Concepto", celda: (f) => f.concepto, principal: true },
          { clave: "valor", encabezado: "Importe", celda: (f) => f.valor, alinear: "fin" },
        ]}
      />,
    );
    const lista = screen.getByRole("list", { name: "Desglose" });
    const fila = within(lista).getByRole("listitem");
    expect(within(fila).getByText("Hotel")).toBeInTheDocument();
    expect(within(fila).getByText("USD 390,00")).toBeInTheDocument();
    expect(within(fila).queryByText("Importe")).not.toBeInTheDocument();
  });
});

describe("EtiquetaEstado", () => {
  it("cada estado lleva texto y símbolo, no solo color", () => {
    render(
      <>
        <EtiquetaEstado estado="aprobado" />
        <EtiquetaEstado estado="revision" />
        <EtiquetaEstado estado="rechazado" />
        <EtiquetaEstado estado="pendiente" />
        <EtiquetaEstado estado="en_curso" />
      </>,
    );
    for (const texto of ["Aprobado", "En revisión", "Rechazado", "Pendiente", "En curso"]) {
      expect(screen.getByText(texto)).toBeInTheDocument();
    }
  });

  it("acepta el texto que manda la API", () => {
    render(<EtiquetaEstado estado="pendiente" texto="Pendiente de aprobación" />);
    expect(screen.getByText("Pendiente de aprobación")).toBeInTheDocument();
  });
});

function ConDialogo({ onConfirmar }: { onConfirmar: () => void }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setAbierto(true)}>
        Rechazar
      </button>
      <DialogoConfirmacion
        abierto={abierto}
        titulo="Rechazar presupuesto"
        efecto="El viaje queda rechazado y la persona verá el motivo."
        confirmar="Rechazar presupuesto"
        peligro
        enviando={false}
        onConfirmar={onConfirmar}
        onCancelar={() => setAbierto(false)}
      >
        <label htmlFor="motivo">Motivo</label>
        <input id="motivo" />
      </DialogoConfirmacion>
    </>
  );
}

describe("DialogoConfirmacion", () => {
  it("explica el efecto, enfoca el primer campo y confirma", async () => {
    const usuario = userEvent.setup();
    const confirmar = vi.fn();
    render(<ConDialogo onConfirmar={confirmar} />);
    await usuario.click(screen.getByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog", { name: "Rechazar presupuesto" });
    expect(dialogo).toHaveAccessibleDescription("El viaje queda rechazado y la persona verá el motivo.");
    expect(within(dialogo).getByLabelText("Motivo")).toHaveFocus();
    await usuario.click(within(dialogo).getByRole("button", { name: "Rechazar presupuesto" }));
    expect(confirmar).toHaveBeenCalledOnce();
  });

  it("Escape cancela y el foco vuelve al botón que lo abrió", async () => {
    const usuario = userEvent.setup();
    render(<ConDialogo onConfirmar={() => {}} />);
    const abrir = screen.getByRole("button", { name: "Rechazar" });
    await usuario.click(abrir);
    await usuario.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(abrir).toHaveFocus();
  });

  it("un clic en el velo no saca el foco del diálogo, y lo de detrás queda inerte", async () => {
    const usuario = userEvent.setup();
    const { container } = render(<ConDialogo onConfirmar={() => {}} />);
    await usuario.click(screen.getByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog");
    expect(container).toHaveAttribute("inert");
    await usuario.click(dialogo.parentElement!);
    expect(dialogo).toContainElement(document.activeElement as HTMLElement);
    await usuario.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(container).not.toHaveAttribute("inert");
  });

  it("con el diálogo abierto, los avisos emergentes siguen fuera de lo inerte y se anuncian", async () => {
    const usuario = userEvent.setup();
    function ConAvisoYDialogo() {
      const { avisar } = useAvisos();
      const [abierto, setAbierto] = useState(true);
      return (
        <DialogoConfirmacion
          abierto={abierto}
          titulo="Rechazar"
          efecto="Efecto."
          confirmar="Confirmar"
          enviando={false}
          onConfirmar={() => avisar({ tono: "exito", texto: "Hecho." })}
          onCancelar={() => setAbierto(false)}
        />
      );
    }
    render(
      <AvisosProvider>
        <ConAvisoYDialogo />
      </AvisosProvider>,
    );
    await usuario.click(screen.getByRole("button", { name: "Confirmar" }));
    const region = screen.getByRole("status", { name: "Avisos" });
    expect(within(region).getByText("Hecho.")).toBeInTheDocument();
    expect(region.closest("[inert]")).toBeNull();
  });

  it("el foco no se escapa del diálogo con Tab", async () => {
    const usuario = userEvent.setup();
    render(<ConDialogo onConfirmar={() => {}} />);
    await usuario.click(screen.getByRole("button", { name: "Rechazar" }));
    const dialogo = screen.getByRole("dialog");
    for (let i = 0; i < 5; i++) {
      await usuario.tab();
      expect(dialogo).toContainElement(document.activeElement as HTMLElement);
    }
  });
});

function Disparador() {
  const { avisar } = useAvisos();
  return (
    <button type="button" onClick={() => avisar({ tono: "exito", texto: "Presupuesto aprobado." })}>
      Aprobar
    </button>
  );
}

describe("Aviso emergente", () => {
  it("anuncia el resultado de una acción y se cierra solo", async () => {
    vi.useFakeTimers();
    try {
      render(
        <AvisosProvider>
          <Disparador />
        </AvisosProvider>,
      );
      act(() => screen.getByRole("button", { name: "Aprobar" }).click());
      expect(within(screen.getByRole("status")).getByText("Presupuesto aprobado.")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(8000));
      expect(screen.queryByText("Presupuesto aprobado.")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("se puede cerrar antes y sale por el mismo camino por el que entró", async () => {
    const usuario = userEvent.setup();
    render(
      <AvisosProvider>
        <Disparador />
      </AvisosProvider>,
    );
    await usuario.click(screen.getByRole("button", { name: "Aprobar" }));
    await usuario.click(screen.getByRole("button", { name: "Cerrar aviso" }));
    // Mientras sale, baja y se desvanece (lo inverso de la entrada); después se quita
    const aviso = screen.getByText("Presupuesto aprobado.").closest("[data-saliendo]");
    expect(aviso).not.toBeNull();
    expect(aviso!.className).toMatch(/translate-y-2/);
    expect(aviso!.className).toMatch(/opacity-0/);
    await waitFor(() => expect(screen.queryByText("Presupuesto aprobado.")).not.toBeInTheDocument());
  });
});

describe("Esqueleto, vacío, migas y encabezado", () => {
  it("el esqueleto anuncia que carga sin mostrar una pantalla en blanco", () => {
    render(<EsqueletoLista texto="Cargando la actividad…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando la actividad…");
  });

  it("el estado vacío explica y ofrece la acción", () => {
    render(
      <EstadoVacio titulo="Aún no tienes viajes" accion={{ href: "/cotizar", texto: "Cotizar mi primer viaje" }}>
        Cuando cotices uno, aparecerá aquí.
      </EstadoVacio>,
    );
    expect(screen.getByRole("heading", { name: "Aún no tienes viajes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cotizar mi primer viaje" })).toHaveAttribute("href", "/cotizar");
  });

  it("las migas dicen dónde estás", () => {
    render(<Migas items={[{ texto: "Gastos", href: "/gastos" }, { texto: "Revisar un gasto" }]} />);
    const migas = screen.getByRole("navigation", { name: "Migas de pan" });
    expect(within(migas).getByRole("link", { name: "Gastos" })).toHaveAttribute("href", "/gastos");
    expect(within(migas).getByText("Revisar un gasto")).toHaveAttribute("aria-current", "page");
  });

  it("el encabezado lleva un solo título y la acción principal", () => {
    render(
      <EncabezadoPagina
        titulo="Resumen"
        descripcion="Cómo va la operación."
        accion={<button type="button">Aprobar viajes</button>}
      />,
    );
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Aprobar viajes" })).toBeInTheDocument();
  });
});
