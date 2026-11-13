import { describe, expect, it } from "vitest";
import { datosDeProyecto, problemasDeProyecto, proporcion, sentidoDiferencia, type DatosProyecto } from "./proyectos";

const VALIDOS: DatosProyecto = {
  nombre: "Torre Norte (aéreo)",
  cliente: "",
  ciudad: "Denver",
  fecha_inicio: "2026-12-15",
  fecha_fin: "2026-12-18",
  moneda: "usd",
};

describe("problemasDeProyecto: las mismas reglas que el servidor", () => {
  it("unos datos completos no tienen problemas", () => {
    expect(problemasDeProyecto(VALIDOS)).toEqual({});
  });

  it("el nombre necesita 3 caracteres sin contar los espacios", () => {
    expect(problemasDeProyecto({ ...VALIDOS, nombre: "  ab  " }).nombre).toBe("El proyecto necesita un nombre.");
  });

  it("las fechas deben existir y la final no puede ir antes de la inicial", () => {
    expect(problemasDeProyecto({ ...VALIDOS, fecha_inicio: "" }).fecha_inicio).toBeTruthy();
    expect(problemasDeProyecto({ ...VALIDOS, fecha_fin: "2026-12-01" }).fecha_fin).toBe(
      "La fecha final no puede ser anterior a la inicial.",
    );
  });

  it("la moneda es un código de tres letras", () => {
    expect(problemasDeProyecto({ ...VALIDOS, moneda: "dólar" }).moneda).toBe(
      "La moneda es un código de tres letras, como USD o EUR.",
    );
    expect(problemasDeProyecto({ ...VALIDOS, moneda: " eur " })).toEqual({});
  });
});

describe("datosDeProyecto", () => {
  it("sin proyecto propone un formulario vacío en USD", () => {
    expect(datosDeProyecto()).toEqual({ nombre: "", cliente: "", ciudad: "", fecha_inicio: "", fecha_fin: "", moneda: "USD" });
  });

  it("con proyecto copia sus datos y deja vacío lo que no tiene", () => {
    const datos = datosDeProyecto({
      id: 3,
      nombre: "Alfama",
      cliente: null,
      ciudad: "Lisboa",
      fecha_inicio: "2026-11-01",
      fecha_fin: "2026-11-05",
      moneda: "EUR",
      viajes: 0,
      gastos: 0,
      previsto_usd: "0.00",
      real_usd: "0.00",
      diferencia_usd: "0.00",
    });
    expect(datos).toEqual({ nombre: "Alfama", cliente: "", ciudad: "Lisboa", fecha_inicio: "2026-11-01", fecha_fin: "2026-11-05", moneda: "EUR" });
  });
});

describe("sentidoDiferencia", () => {
  it("positivo es sobrecosto, negativo es por debajo y cero es igual", () => {
    expect(sentidoDiferencia("12.50")).toBe("sobrecosto");
    expect(sentidoDiferencia("-3.00")).toBe("por_debajo");
    expect(sentidoDiferencia("0.00")).toBe("igual");
    expect(sentidoDiferencia(null)).toBe("igual");
  });
});

describe("proporcion", () => {
  it("es el porcentaje del valor frente al mayor, entre 0 y 100", () => {
    expect(proporcion("50.00", 200)).toBe(25);
    expect(proporcion("300.00", 200)).toBe(100);
    expect(proporcion(null, 200)).toBe(0);
    expect(proporcion("10.00", 0)).toBe(0);
  });
});
