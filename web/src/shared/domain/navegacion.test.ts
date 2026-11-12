import { describe, expect, it } from "vitest";
import { menuPara, origenPantallasActuales, TEXTO_PERMISO } from "./navegacion";

const PLATAFORMA = "http://127.0.0.1:8000";

function textos(permiso: Parameters<typeof menuPara>[0]) {
  return menuPara(permiso, PLATAFORMA).map((e) => e.texto);
}

describe("menú por permiso", () => {
  it("administración ve el resumen, cotizar, viajes, gastos, proyectos y usuarios, en ese orden", () => {
    expect(textos("admin")).toEqual(["Resumen", "Cotizar viaje", "Viajes", "Gastos", "Proyectos", "Usuarios"]);
  });

  it("gestor y colaborador no ven el resumen ni las pantallas de administración", () => {
    for (const permiso of ["gestor", "colaborador"] as const) {
      expect(textos(permiso)).toEqual(["Cotizar viaje", "Viajes", "Gastos"]);
    }
  });

  it("«Cotizar viaje» lleva a /cotizar para todos los permisos", () => {
    for (const permiso of ["admin", "gestor", "colaborador"] as const) {
      expect(menuPara(permiso, PLATAFORMA).find((e) => e.texto === "Cotizar viaje")?.href).toBe("/cotizar");
    }
  });

  it("proyectos y usuarios enlazan a las pantallas actuales de la plataforma, marcadas como externas", () => {
    const menu = menuPara("admin", PLATAFORMA);
    expect(menu.find((e) => e.texto === "Proyectos")).toMatchObject({
      href: "http://127.0.0.1:8000/admin/proyectos",
      externa: true,
    });
    expect(menu.find((e) => e.texto === "Usuarios")).toMatchObject({
      href: "http://127.0.0.1:8000/admin/usuarios",
      externa: true,
    });
    expect(menu.find((e) => e.texto === "Viajes")?.externa).toBe(false);
  });

  it("sin dirección de la plataforma, las pantallas actuales se piden al mismo origen", () => {
    expect(menuPara("admin", "").find((e) => e.texto === "Usuarios")?.href).toBe("/admin/usuarios");
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
