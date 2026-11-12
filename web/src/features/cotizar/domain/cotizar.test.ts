import { describe, expect, it } from "vitest";
import {
  BORRADOR_VACIO,
  agregarAeropuertos,
  borradorDeEjemplo,
  distanciaKm,
  erroresDelServidor,
  idDeRuta,
  ladoDesdeSugerencia,
  pedidoDesdeBorrador,
  problemaDeDecision,
  quitarAeropuerto,
  segmentosCosto,
  textoBusqueda,
  textoDistancia,
  textoOrigenDato,
  validarBorrador,
  type LugarSugerido,
} from "./cotizar";

const MOAB: LugarSugerido = {
  tipo: "lugar",
  id: "5543307",
  nombre: "Moab",
  region: "Utah",
  pais: "Estados Unidos",
  lat: 38.57332,
  lon: -109.54984,
  tambien: null,
  aviso: null,
  origen: "local",
  aeropuertos: [
    { iata: "CNY", nombre: "Canyonlands", municipio: "Moab", km: 26.9, horas: 0.5, grande: false },
    { iata: "GJT", nombre: "Grand Junction", municipio: "Grand Junction", km: 107.7, horas: 2, grande: false },
  ],
};

const SLC: LugarSugerido = {
  ...MOAB,
  tipo: "aeropuerto",
  id: "SLC",
  nombre: "Salt Lake City International Airport",
  region: "Salt Lake City",
  lat: 40.7884,
  lon: -111.978,
  aeropuertos: [{ iata: "SLC", nombre: "Salt Lake City", municipio: "Salt Lake City", km: 0, horas: 0, grande: true }],
};

describe("campo de lugar", () => {
  it("al elegir un lugar quedan sus aeropuertos cercanos y el nombre completo", () => {
    const lado = ladoDesdeSugerencia(MOAB);
    expect(lado.texto).toBe("Moab, Utah, Estados Unidos");
    expect(lado.aeropuertos.map((a) => a.iata)).toEqual(["CNY", "GJT"]);
    expect(lado.lugar?.lat).toBe(38.57332);
  });

  it("un aeropuerto agregado a mano mide su distancia al lugar y no se repite", () => {
    const conSlc = agregarAeropuertos(ladoDesdeSugerencia(MOAB), SLC, { factor: 1.3, velocidad_kmh: 70 });
    const slc = conSlc.aeropuertos.find((a) => a.iata === "SLC")!;
    expect(Math.round(slc.km!)).toBe(Math.round(distanciaKm(38.57332, -109.54984, 40.7884, -111.978)));
    expect(slc.km!).toBeGreaterThan(300);
    expect(textoDistancia(slc)).toMatch(/^\d+ km, unas 6 h por carretera$/);
    expect(agregarAeropuertos(conSlc, SLC, { factor: 1.3, velocidad_kmh: 70 }).aeropuertos).toHaveLength(3);
    expect(quitarAeropuerto(conSlc, "GJT").aeropuertos.map((a) => a.iata)).toEqual(["CNY", "SLC"]);
  });
});

describe("borrador de la cotización", () => {
  it("dice qué falta en cada campo y cómo corregirlo", () => {
    const errores = validarBorrador({ ...BORRADOR_VACIO, ida: "2026-12-10", regreso: "2026-12-09", bateriasN: "-1" });
    expect(errores.proyectoId).toBe("Elige el proyecto del viaje.");
    expect(errores.origen).toMatch(/^Escribe de dónde sale/);
    expect(errores.regreso).toBe("El regreso debe ser después de la ida.");
    expect(errores.bateriasN).toMatch(/entero entre 0 y 50/);
    expect(validarBorrador({ ...borradorDeEjemplo(BORRADOR_VACIO), proyectoId: "1", viajeroId: "1" })).toEqual({});
  });

  it("un lugar elegido sin aeropuertos, o uno a medio agregar, no se puede buscar", () => {
    const sinAeropuertos = { ...ladoDesdeSugerencia(MOAB), aeropuertos: [] };
    expect(validarBorrador({ ...BORRADOR_VACIO, destino: sinAeropuertos }).destino).toMatch(/al menos un aeropuerto/);
    const aMedias = { ...ladoDesdeSugerencia(MOAB), agregando: "SLC" };
    expect(validarBorrador({ ...BORRADOR_VACIO, destino: aMedias }).destino).toMatch(/^Termina de agregar el aeropuerto/);
  });

  it("el pedido omite a quien viaja cuando es la propia persona", () => {
    const b = { ...borradorDeEjemplo(BORRADOR_VACIO), proyectoId: "1", viajeroId: "1" };
    const pedido = pedidoDesdeBorrador(b, 1);
    expect(pedido.viajero_id).toBeNull();
    expect(pedido.destino).toEqual({ texto: "Moab, Utah, Estados Unidos", aeropuertos: ["CNY", "GJT", "SLC"], lugar: b.destino.lugar });
    expect(pedidoDesdeBorrador(b, 3).viajero_id).toBe(1);
    expect(textoBusqueda(pedido)).toBe("Buscando vuelos en 3 aeropuertos (MIA → CNY, GJT, SLC)…");
  });

  it("los campos que señala el servidor caen en el campo del formulario", () => {
    expect(erroresDelServidor({ destino: "No reconozco \"ZZZ\".", "origen.aeropuertos.0": "x", otro: "y" })).toEqual({
      destino: "No reconozco \"ZZZ\".",
      origen: "x",
    });
  });
});

describe("id de la cotización en la dirección", () => {
  it("solo enteros que caben en la base; lo demás es «no encontrado»", () => {
    expect(idDeRuta("12")).toBe(12);
    expect(idDeRuta("2147483647")).toBe(2147483647);
    for (const malo of ["0", "-1", "1.5", "abc", "2147483648", "99999999999999999999", ""]) expect(idDeRuta(malo)).toBeNull();
  });
});

describe("origen del dato", () => {
  it("dice de dónde salen los precios en palabras claras", () => {
    expect(textoOrigenDato("en vivo")).toEqual({ texto: "Precios en vivo", enVivo: true });
    expect(textoOrigenDato("guardado").texto).toBe("Precios guardados");
    expect(textoOrigenDato("guardado (otras fechas)").texto).toBe("Precios guardados de otras fechas");
    expect(textoOrigenDato("fallida").texto).toBe("Sin precios para esta búsqueda");
  });
});

describe("decisión", () => {
  it("apartarse de la recomendada exige el porqué", () => {
    const c = { recomendada_id: 76 };
    expect(problemaDeDecision(c, null, "")?.campo).toBe("vuelo");
    expect(problemaDeDecision(c, 76, "")).toBeNull();
    expect(problemaDeDecision(c, 71, "no")?.campo).toBe("motivo");
    expect(problemaDeDecision(c, 71, "Llega antes")).toBeNull();
  });

  it("la barra solo lleva lo que suma; las millas van aparte", () => {
    const partes = segmentosCosto({
      precio_usd: "415.00",
      equipaje_usd: "230.00",
      riesgo_cambio_usd: "103.75",
      millas_usd: "-24.90",
      traslado_usd: "0.00",
    });
    expect(partes.map((p) => p.tipo)).toEqual(["precio", "equipaje", "riesgo_cambio"]);
    expect(partes[0]).toMatchObject({ nombre: "Precio", valor: "415.00" });
  });
});
