import { describe, expect, it } from "vitest";
import { destinoSeguro } from "@/features/auth/domain/auth";
import { leerBaseApi, leerFuenteDatos } from "./configuracion";

describe("configuración", () => {
  it("FUENTE_DATOS: http por defecto, demo solo si se pide, y error si está mal escrita", () => {
    expect(leerFuenteDatos(undefined)).toBe("http");
    expect(leerFuenteDatos("demo")).toBe("demo");
    expect(() => leerFuenteDatos("demostracion")).toThrow(/FUENTE_DATOS/);
  });

  it("NEXT_PUBLIC_API_BASE: /api/v1 por defecto; rechaza credenciales y protocolos raros", () => {
    expect(leerBaseApi(undefined)).toBe("/api/v1");
    expect(leerBaseApi("http://127.0.0.1:8088/api/v1/")).toBe("http://127.0.0.1:8088/api/v1");
    expect(() => leerBaseApi("https://usuario:clave@api.example.com")).toThrow();
    expect(() => leerBaseApi("javascript:alert(1)")).toThrow();
    expect(() => leerBaseApi("//otro.example.com")).toThrow();
  });

  it("después de entrar solo se vuelve a rutas internas", () => {
    expect(destinoSeguro("/gastos/nuevo")).toBe("/gastos/nuevo");
    expect(destinoSeguro("https://malicioso.example")).toBe("/viajes");
    expect(destinoSeguro("//malicioso.example")).toBe("/viajes");
    expect(destinoSeguro(null)).toBe("/viajes");
  });

  it("no la engañan los caracteres que el navegador quita o cambia al navegar (tabulador, salto de línea, barra invertida)", () => {
    for (const truco of ["/\t/malicioso.example", "/\n/malicioso.example", "/\r\n/malicioso.example", "/ /malicioso.example",
      "/\\malicioso.example", "/viajes\\..\\..\\x"]) {
      expect(destinoSeguro(truco), JSON.stringify(truco)).toBe("/viajes");
    }
    expect(destinoSeguro("/viajes/12?vista=gastos#v3")).toBe("/viajes/12?vista=gastos#v3");
  });
});
