import { describe, expect, it } from "vitest";
import { menuPara, origenPantallasActuales, TEXTO_PERMISO } from "./navegacion";

const PLATAFORMA = "http://127.0.0.1:8000";

function textos(permiso: Parameters<typeof menuPara>[0]) {
  return menuPara(permiso, PLATAFORMA).map((e) => e.texto);
}

describe("menú por permiso", () => {
  it("administración ve todas las pantallas en la web, en este orden", () => {
    expect(textos("admin")).toEqual([
      "Resumen", "Cotizar viaje", "Viajes", "Gastos", "Buzón de correo (simulado)", "KPIs", "Monitoreo", "Vuelos", "Reglas y supuestos", "Proyectos", "Usuarios", "Mi cuenta",
    ]);
  });

  it("el gestor ve sus proyectos; gestor y colaborador no ven las pantallas de administración", () => {
    expect(textos("gestor")).toEqual(["Cotizar viaje", "Viajes", "Gastos", "Proyectos", "Mi cuenta"]);
    expect(textos("colaborador")).toEqual(["Cotizar viaje", "Viajes", "Gastos", "Mi cuenta"]);
  });

  it("«Cotizar viaje» lleva a /cotizar para todos los permisos", () => {
    for (const permiso of ["admin", "gestor", "colaborador"] as const) {
      expect(menuPara(permiso, PLATAFORMA).find((e) => e.texto === "Cotizar viaje")?.href).toBe("/cotizar");
    }
  });

  it("ninguna entrada lleva a las pantallas anteriores: todo está en la web", () => {
    for (const permiso of ["admin", "gestor", "colaborador"] as const) {
      const menu = menuPara(permiso, PLATAFORMA);
      expect(menu.every((e) => !e.externa && e.href.startsWith("/"))).toBe(true);
    }
    expect(menuPara("admin", PLATAFORMA).find((e) => e.texto === "Usuarios")?.href).toBe("/usuarios");
    expect(menuPara("admin", "").map((e) => e.texto)).toEqual(textos("admin"));
  });

  it("a lo sumo cuatro atajos para la barra inferior del celular", () => {
    for (const permiso of ["admin", "gestor", "colaborador"] as const) {
      const atajos = menuPara(permiso, PLATAFORMA).filter((e) => e.atajo);
      expect(atajos.length).toBeGreaterThan(0);
      expect(atajos.length).toBeLessThanOrEqual(4);
      expect(atajos.every((e) => !e.externa)).toBe(true);
    }
  });

  it("cada permiso tiene un nombre para personas", () => {
    expect(TEXTO_PERMISO.admin).toBe("Administración");
    expect(TEXTO_PERMISO.gestor).toBe("Gestión de proyectos");
    expect(TEXTO_PERMISO.colaborador).toBe("Colaboración");
  });
});

describe("origen de las pantallas actuales", () => {
  it("la variable explícita manda y se limpia la barra final", () => {
    expect(origenPantallasActuales("http://127.0.0.1:8000/", "/api/v1")).toBe("http://127.0.0.1:8000");
  });

  it("sin variable, si la API es otro origen, las pantallas están en ese origen", () => {
    expect(origenPantallasActuales(undefined, "http://127.0.0.1:8000/api/v1")).toBe("http://127.0.0.1:8000");
  });

  it("sin variable y con la API en el mismo origen, queda vacío (mismo origen)", () => {
    expect(origenPantallasActuales("", "/api/v1")).toBe("");
  });

  it("rechaza protocolos raros y credenciales", () => {
    expect(() => origenPantallasActuales("javascript:alert(1)", "/api/v1")).toThrow(/NEXT_PUBLIC_PLATAFORMA_URL/);
    expect(() => origenPantallasActuales("https://u:c@ejemplo.com", "/api/v1")).toThrow(/NEXT_PUBLIC_PLATAFORMA_URL/);
  });
});
