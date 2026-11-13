import { describe, expect, it } from "vitest";
import { bienvenidaDe, bloquesDeTexto, duracionLegible, preguntasSugeridas, reloj, rutaDeFuente } from "./asistente";
import { codificarWav } from "./audio";

describe("rutaDeFuente", () => {
  it("enlaza cada fuente a su pantalla de esta web", () => {
    expect(rutaDeFuente({ tipo: "gasto", id: 12 })).toBe("/gastos/12");
    expect(rutaDeFuente({ tipo: "viaje", id: 3 })).toBe("/viajes/3");
    expect(rutaDeFuente({ tipo: "cotizacion", id: 7 })).toBe("/cotizar/7");
  });

  it("sin destino o con un id que no es un entero positivo no enlaza", () => {
    expect(rutaDeFuente(null)).toBeNull();
    expect(rutaDeFuente({ tipo: "gasto", id: 0 })).toBeNull();
    expect(rutaDeFuente({ tipo: "gasto", id: 1.5 })).toBeNull();
  });
});

describe("bloquesDeTexto", () => {
  it("separa párrafos y viñetas y respeta las negritas como dato", () => {
    const bloques = bloquesDeTexto("Hay **2 gastos** en revisión.\n\n- gasto #4: sin recibo\n- gasto #9: <b>duplicado</b>\nRevisa primero el #4.");
    expect(bloques).toEqual([
      {
        tipo: "parrafo",
        segmentos: [
          { texto: "Hay ", negrita: false },
          { texto: "2 gastos", negrita: true },
          { texto: " en revisión.", negrita: false },
        ],
      },
      {
        tipo: "lista",
        ordenada: false,
        items: [[{ texto: "gasto #4: sin recibo", negrita: false }], [{ texto: "gasto #9: <b>duplicado</b>", negrita: false }]],
      },
      { tipo: "parrafo", segmentos: [{ texto: "Revisa primero el #4.", negrita: false }] },
    ]);
  });

  it("las listas numeradas quedan ordenadas y los títulos en negrita", () => {
    const bloques = bloquesDeTexto("### Resumen\n1. Uno\n2. Dos");
    expect(bloques[0]).toEqual({ tipo: "parrafo", segmentos: [{ texto: "Resumen", negrita: true }] });
    expect(bloques[1]).toMatchObject({ tipo: "lista", ordenada: true });
  });
});

describe("formato", () => {
  it("duración con coma decimal y reloj de grabación", () => {
    expect(duracionLegible(7842)).toBe("7,8 s");
    expect(reloj(7)).toBe("0:07");
    expect(reloj(65)).toBe("1:05");
  });
});

describe("codificarWav", () => {
  it("escribe una cabecera WAV PCM mono de 16 bits y recorta las muestras fuera de rango", () => {
    const wav = codificarWav(new Float32Array([0, 1, -1, 2]), 16000);
    const vista = new DataView(wav);
    const texto = (desde: number) => String.fromCharCode(...new Uint8Array(wav, desde, 4));
    expect(texto(0)).toBe("RIFF");
    expect(texto(8)).toBe("WAVE");
    expect(vista.getUint16(22, true)).toBe(1);
    expect(vista.getUint32(24, true)).toBe(16000);
    expect(vista.getUint32(40, true)).toBe(8);
    expect(vista.getInt16(46, true)).toBe(0x7fff);
    expect(vista.getInt16(48, true)).toBe(-0x8000);
    expect(vista.getInt16(50, true)).toBe(0x7fff);
  });
});

describe("según el permiso", () => {
  it("colaborador y gestor reciben preguntas sobre lo suyo; administración, las de la empresa", () => {
    const propias = ["¿Cuánto me queda del presupuesto?", "¿Por qué mi gasto quedó en revisión?", "¿Qué me falta por justificar?"];
    expect(preguntasSugeridas("colaborador")).toEqual(propias);
    expect(preguntasSugeridas("gestor")).toEqual(propias);
    expect(preguntasSugeridas("admin")).toContain("¿Cómo van los indicadores?");
    expect(preguntasSugeridas("admin").some((p) => propias.includes(p))).toBe(false);
  });

  it("la bienvenida dice qué puede ver cada uno", () => {
    expect(bienvenidaDe("colaborador")).toContain("Solo ves lo tuyo.");
    expect(bienvenidaDe("gestor")).toContain("proyectos que gestionas");
    expect(bienvenidaDe("admin")).toContain("indicadores");
  });
});
