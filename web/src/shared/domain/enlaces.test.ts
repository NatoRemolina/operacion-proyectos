import { describe, expect, it } from "vitest";
import { esEnlaceExterno, esRutaPropia } from "./enlaces";

describe("esquema común de los enlaces que se pintan en un href (B7)", () => {
  it("una ruta propia empieza con una sola barra y no trae caracteres que el navegador reinterprete", () => {
    for (const bueno of ["/api/v1/cotizaciones/12/vuelos/3/vendedor", "/viajes/9", "/gastos?estado=revision"]) {
      expect(esRutaPropia(bueno), bueno).toBe(true);
    }
    for (const malo of [
      "", "viajes", "//otro.test/x", "/\\otro.test", "/viajes\\..\\x", "javascript:alert(1)", "https://otro.test/",
      "/con espacio", "/salto\nde-linea", "data:text/html,<b>x</b>",
    ]) {
      expect(esRutaPropia(malo), JSON.stringify(malo)).toBe(false);
    }
  });

  it("un enlace a otro sitio es https, sin credenciales ni puerto, y del sitio que se espera", () => {
    expect(esEnlaceExterno("https://t.me/operacion_bot?start=abc123", ["t.me"])).toBe(true);
    expect(esEnlaceExterno("https://www.iata.org/es/programs/", undefined)).toBe(true);
    for (const malo of [
      "http://t.me/operacion_bot?start=abc", "https://t.me.otro.test/x", "https://otro.test/?r=t.me",
      "https://usuario:clave@t.me/x", "https://t.me:8443/x", "javascript:alert(1)", "//t.me/x", "t.me/x", " https://t.me/x",
    ]) {
      expect(esEnlaceExterno(malo, ["t.me"]), malo).toBe(false);
    }
  });

  it("se puede admitir http donde no hay nada que proteger (la fuente escrita de una regla)", () => {
    expect(esEnlaceExterno("http://www.faa.gov/hazmat", undefined, ["http:", "https:"])).toBe(true);
    expect(esEnlaceExterno("ftp://www.faa.gov/hazmat", undefined, ["http:", "https:"])).toBe(false);
  });
});
