import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { propiedades, sintetizar } from "./ayuda";

describe("trabajador de capturas (función Tareas, pieza 5)", () => {
  const { api } = sintetizar();
  const recursos = api.findResources("AWS::Lambda::Function");
  const id = (pred: (p: any) => boolean) => Object.keys(recursos).find((k) => pred(recursos[k].Properties));
  const idTareas = id((p) => p.Environment?.Variables?.TAREAS === "capturas");
  const idWeb = id((p) => p.Environment?.Variables?.ANALIZADOR_FUNCION && !p.Environment?.Variables?.TAREAS);
  const idAnalizador = id((p) => p.Environment?.Variables?.ANALIZADOR === "encendido");
  const tareas = idTareas ? recursos[idTareas].Properties : undefined;

  test("usa la imagen de la API con otro punto de entrada y 15 minutos como máximo", () => {
    assert.ok(tareas, "falta la función Tareas");
    assert.equal(tareas.PackageType, "Image");
    assert.equal(JSON.stringify(tareas.Code), JSON.stringify(recursos[idWeb!].Properties.Code), "misma imagen que la API");
    assert.deepEqual(tareas.ImageConfig.Command, ["sh", "-c", "exec uvicorn app.tareas:aplicacion --host 0.0.0.0 --port ${PORT}"]);
    assert.equal(tareas.Timeout, 900);
    assert.deepEqual(tareas.Architectures, ["arm64"]);
    assert.equal(tareas.ReservedConcurrentExecutions, undefined);
  });

  test("lee el secreto de la base, sabe a qué analizador llamar y no tiene dirección pública", () => {
    const v = tareas.Environment.Variables;
    assert.ok(v.SECRETO_ARN, "falta el secreto");
    assert.deepEqual(v.ANALIZADOR_FUNCION, { Ref: idAnalizador });
    assert.equal(propiedades(api, "AWS::Lambda::Url").length, 1, "solo la API tiene dirección");
  });

  test("su propio rol: puede invocar al analizador y leer el secreto, nada más de lambda", () => {
    const rol = tareas.Role["Fn::GetAtt"][0];
    assert.notEqual(rol, recursos[idWeb!].Properties.Role["Fn::GetAtt"][0], "no comparte el rol de la API");
    const politicas = Object.values(api.findResources("AWS::IAM::Policy"))
      .filter((p: any) => p.Properties.Roles.some((r: any) => r.Ref === rol))
      .flatMap((p: any) => p.Properties.PolicyDocument.Statement);
    const acciones = politicas.flatMap((s: any) => [s.Action].flat());
    assert.ok(acciones.includes("lambda:InvokeFunction"));
    assert.ok(acciones.some((a: string) => a.startsWith("secretsmanager:GetSecretValue")));
    assert.ok(acciones.every((a: string) => /^(lambda:InvokeFunction|secretsmanager:(GetSecretValue|DescribeSecret))$/.test(a)), acciones.join());
  });

  test("una regla de EventBridge la llama cada 15 minutos, sin reintentos", () => {
    const reglas = propiedades(api, "AWS::Events::Rule");
    assert.equal(reglas.length, 1);
    assert.equal(reglas[0].ScheduleExpression, "rate(15 minutes)");
    assert.deepEqual(reglas[0].Targets[0].Arn, { "Fn::GetAtt": [idTareas, "Arn"] });
    assert.equal(reglas[0].Targets[0].RetryPolicy.MaximumRetryAttempts, 0);
    const permisos = propiedades(api, "AWS::Lambda::Permission").filter((p) => p.Principal === "events.amazonaws.com");
    assert.equal(permisos.length, 1);
  });
});
