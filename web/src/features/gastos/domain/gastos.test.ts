import { describe, expect, it } from "vitest";
import { etiquetaCategoria, mesEnCurso, problemaDePeriodo, validarArchivo } from "./gastos";

describe("archivo del recibo", () => {
  it("el tope es el mismo que el del servidor (4,5 MB, no 4,5 MiB)", () => {
    expect(validarArchivo({ size: 4_500_000, type: "image/jpeg", name: "recibo.jpg" })).toBeNull();
    expect(validarArchivo({ size: 4_600_000, type: "image/jpeg", name: "recibo.jpg" })).toBe("demasiado_grande");
  });

  it("acepta el correo de una reserva (.eml) aunque el navegador no le ponga tipo o le ponga uno genérico", () => {
    for (const type of ["message/rfc822", "", "application/octet-stream"]) {
      expect(validarArchivo({ size: 2_000, type, name: "correo_tiquete.eml" }), type).toBeNull();
    }
    expect(validarArchivo({ size: 2_000, type: "application/octet-stream", name: "programa.exe" })).toBe("tipo_no_admitido");
  });

  it("acepta la confirmación de una reserva en HTML (.html o .htm), con o sin tipo", () => {
    const casos: [string, string][] = [
      ["text/html", "confirmacion_hotel.html"],
      ["", "reserva.htm"],
      ["application/octet-stream", "reserva.html"],
    ];
    for (const [type, name] of casos) {
      expect(validarArchivo({ size: 2_000, type, name }), name).toBeNull();
    }
    expect(validarArchivo({ size: 2_000, type: "text/html", name: "pagina.php" })).toBe("tipo_no_admitido");
  });
});

describe("periodo del Excel contable", () => {
  it("por omisión es el mes en curso, del primer al último día, en la fecha local", () => {
    expect(mesEnCurso(new Date(2026, 1, 14, 23, 59))).toEqual({ desde: "2026-02-01", hasta: "2026-02-28" });
    expect(mesEnCurso(new Date(2028, 1, 3))).toEqual({ desde: "2028-02-01", hasta: "2028-02-29" });
    expect(mesEnCurso(new Date(2026, 11, 31))).toEqual({ desde: "2026-12-01", hasta: "2026-12-31" });
  });

  it("exige las dos fechas y que la final no sea anterior a la inicial, como el servidor", () => {
    expect(problemaDePeriodo({ desde: "2026-11-01", hasta: "2026-11-30" })).toBeNull();
    expect(problemaDePeriodo({ desde: "2026-11-30", hasta: "2026-11-30" })).toBeNull();
    expect(problemaDePeriodo({ desde: "2026-11-30", hasta: "2026-11-01" })).toMatch(/final no puede ser anterior/);
    expect(problemaDePeriodo({ desde: "", hasta: "2026-11-30" })).toMatch(/Elige/);
    expect(problemaDePeriodo({ desde: "2026-11-01", hasta: "30/11/2026" })).toMatch(/Elige/);
  });
});

describe("categoría del gasto", () => {
  it("muestra el nombre de la categoría, incluidas transporte terrestre y compras del proyecto", () => {
    expect(etiquetaCategoria("transporte_terrestre")).toBe("Transporte terrestre: taxi, bus, tren, aplicación");
    expect(etiquetaCategoria("compras_proyecto")).toBe("Compras del proyecto");
    expect(etiquetaCategoria("comida")).toBe("Comida");
  });

  it("sin categoría dice que falta confirmarla, y un nombre ya legible se muestra tal cual", () => {
    expect(etiquetaCategoria(null)).toBe("Por confirmar");
    expect(etiquetaCategoria("Alimentación")).toBe("Alimentación");
  });
});
