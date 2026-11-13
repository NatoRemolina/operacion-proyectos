import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { propiedades, sintetizar } from "./ayuda";

describe("analizador de la página del vuelo (Google Flights)", () => {
  const { api } = sintetizar();
  const funciones = propiedades(api, "AWS::Lambda::Function");
  const analizador = funciones.find((f) => f.Environment?.Variables?.ANALIZADOR === "encendido");
  const web = funciones.find((f) => f.Environment?.Variables?.ANALIZADOR_FUNCION);

  test("es una función aparte con su propia imagen, un minuto como máximo y memoria propia", () => {
    assert.ok(analizador, "falta la función del analizador");
    assert.equal(analizador.PackageType, "Image");
    assert.equal(analizador.Timeout, 60);
    assert.equal(analizador.MemorySize, 2048);
    assert.deepEqual(analizador.Architectures, ["arm64"]);
    assert.deepEqual(analizador.ImageConfig, {
      EntryPoint: ["python", "-m", "awslambdaric"], Command: ["analizador.lambda_handler.handler"],
    });
    assert.notEqual(JSON.stringify(analizador.Code), JSON.stringify(web.Code), "no comparte la imagen de la API");
  });

  test("no recibe secretos: solo el interruptor y su carpeta de trabajo", () => {
    assert.deepEqual(Object.keys(analizador.Environment.Variables).sort(), ["ANALIZADOR", "HOME"]);
  });

  test("la API sabe a quién llamar y tiene permiso para invocarla; nadie más", () => {
    assert.deepEqual(web.Environment.Variables.ANALIZADOR_FUNCION, { Ref: Object.keys(api.findResources("AWS::Lambda::Function"))
      .find((id) => api.findResources("AWS::Lambda::Function")[id].Properties.Environment?.Variables?.ANALIZADOR === "encendido") });
    const politicas = propiedades(api, "AWS::IAM::Policy").flatMap((p) => p.PolicyDocument.Statement);
    const invocar = politicas.filter((s) => [s.Action].flat().includes("lambda:InvokeFunction"));
    assert.equal(invocar.length, 1);
    assert.equal(propiedades(api, "AWS::Lambda::Url").length, 1, "el analizador no tiene dirección pública");
  });
});
