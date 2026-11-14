import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { CON_DOMINIO, propiedades, sintetizar } from "./ayuda";

const { api, web } = sintetizar(CON_DOMINIO);

/** El id lógico de la función cuyas variables cumplen la condición. */
function funcion(plantilla: any, cumple: (v: Record<string, unknown>) => boolean): string {
  const recursos = plantilla.findResources("AWS::Lambda::Function");
  const id = Object.keys(recursos).find((k) => cumple(recursos[k].Properties.Environment?.Variables ?? {}));
  assert.ok(id, "no se encontró la función");
  return id;
}

/** Las alarmas de una métrica de Lambda sobre esa función. */
function alarmasDe(plantilla: any, idFuncion: string) {
  return propiedades(plantilla, "AWS::CloudWatch::Alarm").filter(
    (a) => a.Namespace === "AWS/Lambda" && (a.Dimensions ?? []).some((d: any) => d.Name === "FunctionName" && d.Value?.Ref === idFuncion),
  );
}

const avisa = (a: any) => JSON.stringify(a.AlarmActions ?? []).includes("OperacionBase");

function comprobarFuncion(plantilla: any, idFuncion: string, limiteMs: number) {
  const alarmas = alarmasDe(plantilla, idFuncion);
  const de = (metrica: string) => alarmas.find((a) => a.MetricName === metrica);
  for (const metrica of ["Errors", "Throttles"]) {
    const a = de(metrica);
    assert.ok(a, `falta la alarma de ${metrica}`);
    assert.equal(a.Threshold, 1);
    assert.ok(avisa(a), `${metrica} no avisa`);
  }
  const duracion = de("Duration");
  assert.ok(duracion, "falta la alarma de duración");
  assert.equal(duracion.Statistic, "Maximum");
  assert.ok(duracion.Threshold < limiteMs && duracion.Threshold >= limiteMs * 0.8,
    `la duración avisa cerca del límite (${limiteMs} ms), no en ${duracion.Threshold}`);
  assert.ok(avisa(duracion));
}

describe("alarmas del analizador, Tareas, la web y CloudFront (B2)", () => {
  test("analizador: fallos, rechazos y duración cerca de su minuto", () => {
    comprobarFuncion(api, funcion(api, (v) => v.ANALIZADOR === "encendido"), 60_000);
  });

  test("Tareas: fallos, rechazos y duración cerca de sus 15 minutos", () => {
    comprobarFuncion(api, funcion(api, (v) => v.TAREAS === "capturas"), 15 * 60_000);
  });

  test("función de la web: fallos, rechazos, duración cerca de sus 30 s y respuestas 5xx de su dirección", () => {
    const id = funcion(web, () => true);
    comprobarFuncion(web, id, 30_000);
    const url5xx = propiedades(web, "AWS::CloudWatch::Alarm").find((a) => a.MetricName === "Url5xxCount");
    assert.ok(url5xx, "falta la alarma de 5xx de la dirección de la web");
    assert.equal(url5xx.Statistic, "Sum");
    assert.ok(avisa(url5xx));
  });

  test("CloudFront: tasa de 5xx de cada distribución (web y administración), sostenida", () => {
    const distribuciones = Object.keys(web.findResources("AWS::CloudFront::Distribution"));
    const alarmas = propiedades(web, "AWS::CloudWatch::Alarm").filter((a) => a.MetricName === "5xxErrorRate");
    assert.equal(alarmas.length, 2);
    for (const id of distribuciones) {
      const a = alarmas.find((x) => x.Dimensions.some((d: any) => d.Name === "DistributionId" && d.Value?.Ref === id));
      assert.ok(a, `falta la alarma de la distribución ${id}`);
      assert.equal(a.Namespace, "AWS/CloudFront");
      assert.deepEqual(a.Dimensions.find((d: any) => d.Name === "Region"), { Name: "Region", Value: "Global" });
      // Con poco tráfico un solo 504 es mucho porcentaje: se pide que se sostenga dos periodos
      assert.equal(a.EvaluationPeriods, 2);
      assert.equal(a.DatapointsToAlarm, 2);
      assert.ok(avisa(a));
    }
  });

  test("toda alarma de las pilas avisa al tema que ya existe; ninguna pila crea otro", () => {
    for (const plantilla of [api, web]) {
      for (const a of propiedades(plantilla, "AWS::CloudWatch::Alarm")) assert.ok(avisa(a), `${a.MetricName} no avisa`);
      plantilla.resourceCountIs("AWS::SNS::Topic", 0);
    }
  });
});
