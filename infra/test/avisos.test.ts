import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { propiedades, sintetizar } from "./ayuda";

describe("alarmas de la API (H-37)", () => {
  const { api } = sintetizar();
  const alarmas = propiedades(api, "AWS::CloudWatch::Alarm");
  const avisan = (a: any) => JSON.stringify(a.AlarmActions).includes("OperacionBase");

  test("cuenta las líneas ERROR peticion= del registro de la función", () => {
    const [filtro, ...otros] = propiedades(api, "AWS::Logs::MetricFilter");
    assert.equal(otros.length, 0);
    assert.equal(filtro.FilterPattern, '"ERROR peticion="');
    assert.deepEqual(filtro.MetricTransformations.map((m: any) => m.MetricValue), ["1"]);
    const { MetricNamespace, MetricName } = filtro.MetricTransformations[0];
    const alarma = alarmas.find((a) => a.MetricName === MetricName && a.Namespace === MetricNamespace);
    assert.ok(alarma, "falta la alarma de errores de la aplicación");
    assert.equal(alarma.Threshold, 1);
    assert.equal(alarma.ComparisonOperator, "GreaterThanOrEqualToThreshold");
    assert.ok(avisan(alarma));
  });

  test("avisa cuando la dirección de la función responde 5xx", () => {
    const alarma = alarmas.find((a) => a.MetricName === "Url5xxCount");
    assert.ok(alarma, "falta la alarma de Url5xxCount");
    assert.equal(alarma.Namespace, "AWS/Lambda");
    assert.equal(alarma.Statistic, "Sum");
    assert.equal(alarma.Threshold, 1);
    assert.deepEqual(alarma.Dimensions.map((d: any) => d.Name).sort(), ["FunctionName", "Resource"]);
    assert.ok(avisan(alarma));
  });

  test("las alarmas que ya había siguen", () => {
    const nombres = alarmas.map((a) => a.MetricName).sort();
    for (const m of ["Duration", "Errors", "Throttles"]) assert.ok(nombres.includes(m), `falta ${m}`);
  });
});

describe("correo de avisos (H-36)", () => {
  test("sin -c correo no se sintetiza: CloudFormation borraría la suscripción de las alarmas", () => {
    assert.throws(() => sintetizar({ correo: "" }), /-c correo=/);
    assert.throws(() => sintetizar({ correo: "sin-arroba" }), /-c correo=/);
  });

  test("con correo, la suscripción de las alarmas siempre está", () => {
    const { base } = sintetizar({ correo: "avisos@example.com" });
    const [suscripcion, ...otras] = propiedades(base, "AWS::SNS::Subscription");
    assert.equal(otras.length, 0);
    assert.equal(suscripcion.Protocol, "email");
    assert.equal(suscripcion.Endpoint, "avisos@example.com");
  });

  test("el presupuesto es el de la cuenta («cuenta-mensual», de la titular de la cuenta): la pila no crea otro", () => {
    const { base, api, web } = sintetizar();
    for (const plantilla of [base, api, web]) plantilla.resourceCountIs("AWS::Budgets::Budget", 0);
  });
});
