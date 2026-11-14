import { describe, expect, it } from "vitest";
import nextConfig from "../../next.config";
import { politicaDeContenido } from "./cabeceras";

function directivas(csp: string): Record<string, string[]> {
  return Object.fromEntries(csp.split(";").map((d) => d.trim().split(/\s+/)).filter((d) => d[0]).map(([n, ...v]) => [n!, v]));
}

describe("política de contenido (CSP) de la web (B1)", () => {
  it("en producción solo carga lo propio: sin eval, sin objetos, sin enmarcado ajeno ni formularios a otro sitio", () => {
    const d = directivas(politicaDeContenido({ desarrollo: false, baseApi: "/api/v1" }));
    expect(d["default-src"]).toEqual(["'self'"]);
    expect(d["script-src"]).not.toContain("'unsafe-eval'");
    expect(d["script-src"]).not.toContain("*");
    expect(d["connect-src"]).toEqual(["'self'"]);
    expect(d["object-src"]).toEqual(["'none'"]);
    expect(d["frame-ancestors"]).toEqual(["'self'"]);
    expect(d["base-uri"]).toEqual(["'self'"]);
    expect(d["form-action"]).toEqual(["'self'"]);
    // la vista previa del recibo y la nota de voz usan blob:
    expect(d["img-src"]).toContain("blob:");
    expect(d["media-src"]).toContain("blob:");
  });

  it("si la API está en otro origen (desarrollo sin gateway), la admite solo a ella", () => {
    const d = directivas(politicaDeContenido({ desarrollo: false, baseApi: "http://127.0.0.1:8000/api/v1" }));
    expect(d["connect-src"]).toEqual(["'self'", "http://127.0.0.1:8000"]);
    expect(d["img-src"]).toContain("http://127.0.0.1:8000");
  });

  it("en desarrollo admite lo que necesita la recarga en caliente de Next", () => {
    const d = directivas(politicaDeContenido({ desarrollo: true, baseApi: "/api/v1" }));
    expect(d["script-src"]).toContain("'unsafe-eval'");
  });

  it("Next la pone en todas las rutas", async () => {
    const reglas = await nextConfig.headers!();
    const todas = reglas.find((r) => r.source === "/:path*");
    expect(todas?.headers.find((h) => h.key === "Content-Security-Policy")?.value).toMatch(/default-src 'self'/);
  });
});
