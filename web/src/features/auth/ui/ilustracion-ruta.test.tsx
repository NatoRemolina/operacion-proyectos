import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IlustracionRuta } from "./ilustracion-ruta";

type Punto = { x: number; y: number };
type Codigo = "MDE" | "LAX" | "SFO" | "JFK" | "MIA";

// Lienzo del SVG; las etiquetas se ubican en porcentaje de él.
const ANCHO = 640;
const ALTO = 360;

function montar() {
  const { container } = render(<IlustracionRuta />);
  return { raiz: container.firstElementChild as HTMLElement, svg: container.querySelector("svg")! };
}

const numeros = (d: string) => (d.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);

function puntos(d: string): Punto[] {
  const v = numeros(d);
  return Array.from({ length: v.length / 2 }, (_, i) => ({ x: v[2 * i]!, y: v[2 * i + 1]! }));
}

function caja(ps: Punto[]) {
  const xs = ps.map((p) => p.x);
  const ys = ps.map((p) => p.y);
  return { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
}

const dentro = (p: Punto, c: ReturnType<typeof caja>) => p.x >= c.x0 && p.x <= c.x1 && p.y >= c.y0 && p.y <= c.y1;
const distancia = (a: Punto, b: Punto) => Math.hypot(a.x - b.x, a.y - b.y);

/** Posición de cada ciudad en el lienzo, leída de su etiqueta. */
function ciudades(raiz: HTMLElement): Record<Codigo, Punto> {
  const resultado: Partial<Record<Codigo, Punto>> = {};
  raiz.querySelectorAll<HTMLElement>(".portada-etiqueta").forEach((etiqueta) => {
    const codigo = etiqueta.firstElementChild!.textContent as Codigo;
    resultado[codigo] = {
      x: (parseFloat(etiqueta.style.left) / 100) * ANCHO,
      y: (parseFloat(etiqueta.style.top) / 100) * ALTO,
    };
  });
  return resultado as Record<Codigo, Punto>;
}

/** Arco cuadrático «M a Q control b», muestreado. */
function muestrear(d: string): Punto[] {
  const [a, c, b] = puntos(d) as [Punto, Punto, Punto];
  return Array.from({ length: 101 }, (_, i) => {
    const t = i / 100;
    return {
      x: (1 - t) ** 2 * a.x + 2 * t * (1 - t) * c.x + t * t * b.x,
      y: (1 - t) ** 2 * a.y + 2 * t * (1 - t) * c.y + t * t * b.y,
    };
  });
}

const segundos = (valor: string) => parseFloat(valor);
const dinero = (texto: string) => Number(texto.replace(/[^\d,]/g, "").replace(",", "."));

describe("Ilustración de la portada", () => {
  it("es decorativa: los lectores de pantalla la omiten y no tiene nada enfocable", () => {
    const { raiz } = montar();
    expect(raiz).toHaveAttribute("aria-hidden", "true");
    expect(raiz.querySelectorAll("a, button, input, [tabindex]")).toHaveLength(0);
  });

  it("dibuja Colombia y Estados Unidos con contornos de 40 a 80 puntos", () => {
    const { svg } = montar();
    for (const relleno of ["var(--carta-tierra)", "var(--carta-origen)"]) {
      const contorno = svg.querySelector(`path[fill="${relleno}"]`)!;
      const cantidad = puntos(contorno.getAttribute("d")!).length;
      expect(cantidad).toBeGreaterThanOrEqual(40);
      expect(cantidad).toBeLessThanOrEqual(80);
    }
  });

  it("pone el norte arriba y cada ciudad dentro de su país", () => {
    const { raiz, svg } = montar();
    const c = ciudades(raiz);
    expect(Object.keys(c).sort()).toEqual(["JFK", "LAX", "MDE", "MIA", "SFO"]);

    const eeuu = caja(puntos(svg.querySelector('path[fill="var(--carta-tierra)"]')!.getAttribute("d")!));
    const colombia = caja(puntos(svg.querySelector('path[fill="var(--carta-origen)"]')!.getAttribute("d")!));
    expect(dentro(c.MDE, colombia)).toBe(true);
    for (const codigo of ["LAX", "SFO", "JFK", "MIA"] as const) expect(dentro(c[codigo], eeuu)).toBe(true);

    // Colombia queda al sur; San Francisco, al norte de Los Ángeles; Nueva York, al este de la costa oeste.
    expect(colombia.y0).toBeGreaterThan(eeuu.y1);
    expect(c.SFO.y).toBeLessThan(c.LAX.y);
    expect(c.SFO.x).toBeLessThan(c.LAX.x);
    expect(c.JFK.x).toBeGreaterThan(c.LAX.x);
    expect(c.MIA.y).toBeGreaterThan(c.JFK.y);
  });

  it("hace salir las cuatro rutas de Medellín y destaca la de Los Ángeles", () => {
    const { raiz, svg } = montar();
    const c = ciudades(raiz);
    const rutas = [...svg.querySelectorAll(":scope > path[mask]")];
    expect(rutas).toHaveLength(4);

    const destinos = rutas.map((ruta) => {
      const ps = puntos(ruta.getAttribute("d")!);
      expect(distancia(ps[0]!, c.MDE)).toBeLessThan(0.5);
      const fin = ps.at(-1)!;
      return (Object.keys(c) as Codigo[]).find((codigo) => distancia(c[codigo], fin) < 0.5);
    });
    expect(destinos.sort()).toEqual(["JFK", "LAX", "MIA", "SFO"]);

    const destacadas = rutas.filter((ruta) => ruta.getAttribute("stroke") === "var(--marca)");
    expect(destacadas).toHaveLength(1);
    const principal = destacadas[0]!;
    const finPrincipal = puntos(principal.getAttribute("d")!).at(-1)!;
    expect(distancia(finPrincipal, c.LAX)).toBeLessThan(0.5);
    for (const ruta of rutas.filter((r) => r !== principal)) {
      expect(Number(ruta.getAttribute("stroke-width"))).toBeLessThan(Number(principal.getAttribute("stroke-width")));
    }
  });

  it("no pasa ninguna ruta por encima de otra ciudad", () => {
    const { raiz, svg } = montar();
    const c = ciudades(raiz);
    for (const ruta of svg.querySelectorAll(":scope > path[mask]")) {
      const muestra = muestrear(ruta.getAttribute("d")!);
      const fin = muestra.at(-1)!;
      for (const [codigo, punto] of Object.entries(c)) {
        if (codigo === "MDE" || distancia(punto, fin) < 0.5) continue;
        const cercania = Math.min(...muestra.map((p) => distancia(p, punto)));
        expect(cercania, `la ruta a ${codigo} queda demasiado cerca`).toBeGreaterThan(20);
      }
    }
  });

  it("dibuja las rutas una tras otra y el viaje nace cuando llega la principal", () => {
    const { raiz, svg } = montar();
    const trazos = [...svg.querySelectorAll<SVGPathElement>("mask path")].map((p) => ({
      inicio: segundos(p.style.animationDelay),
      fin: segundos(p.style.animationDelay) + segundos(p.style.animationDuration),
    }));
    expect(trazos).toHaveLength(4);
    trazos.slice(1).forEach((trazo, i) => expect(trazo.inicio).toBeGreaterThan(trazos[i]!.inicio));

    // La última en llegar es la principal (la máscara de la ruta a Los Ángeles).
    const principal = svg.querySelector('path[stroke="var(--marca)"]')!.getAttribute("mask")!;
    const ultima = [...svg.querySelectorAll("mask")].at(-1)!;
    expect(principal).toBe(`url(#${ultima.id})`);

    const tarjeta = [...raiz.querySelectorAll(".portada-aparece")].find((e) => e.textContent!.includes("Medellín"))!;
    const nace = segundos(tarjeta.className.match(/animation-delay:([\d.]+)s/)![1]!);
    expect(nace).toBeGreaterThanOrEqual(Math.max(...trazos.map((t) => t.fin)) - 0.05);
  });

  it("cuenta el mismo viaje en la tarjeta y en el recibo, con cifras que cuadran", () => {
    const { raiz } = montar();
    expect(raiz).toHaveTextContent("Medellín → Los Ángeles");
    expect(raiz).toHaveTextContent("LOS ANGELES, CA");

    const antes = dinero(raiz.querySelector(".portada-cifra-antes")!.textContent!);
    const despues = dinero(raiz.querySelector(".portada-cifra-despues")!.textContent!);
    const total = [...raiz.querySelectorAll("p")].find((p) => p.textContent!.startsWith("TOTAL USD"))!;
    const hotel = Number(total.textContent!.replace("TOTAL USD", ""));
    expect(Math.round((antes + hotel) * 100)).toBe(Math.round(despues * 100));

    // La barra de ejecución termina en la proporción del presupuesto que se gastó.
    const presupuesto = dinero(raiz.querySelector(".portada-cifra-despues")!.parentElement!.parentElement!.textContent!.split("de")[1]!);
    const barra = raiz.querySelector<HTMLElement>(".portada-ejecucion")!;
    const ancho = Number(barra.className.match(/w-\[(\d+)%\]/)![1]);
    expect(Math.abs(ancho - (despues / presupuesto) * 100)).toBeLessThan(1);
  });
});
