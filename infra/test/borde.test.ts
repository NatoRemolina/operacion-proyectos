import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { CON_DOMINIO, DOMINIO, propiedades, sintetizar } from "./ayuda";

const WEB = `software.${DOMINIO}`;

function distribuciones(contexto: Record<string, string>) {
  const { web } = sintetizar(contexto);
  const ds = propiedades(web, "AWS::CloudFront::Distribution").map((p) => p.DistributionConfig);
  return { plantilla: web, web: ds.find((d) => d.Aliases[0] === WEB), admin: ds.find((d) => d.Aliases[0] !== WEB) };
}

const origen = (d: any, id: string) => d.Origins.find((o: any) => o.Id === id);
const idApi = (web: any) => web.CacheBehaviors.find((c: any) => c.PathPattern === "/api/v1/*").TargetOriginId;

describe("WAF en el borde, con interruptor (B1)", () => {
  test("sin -c waf=1 no se crea: cuesta unos 7 USD al mes y el presupuesto de la cuenta es de 5", () => {
    const { plantilla, web, admin } = distribuciones(CON_DOMINIO);
    plantilla.resourceCountIs("AWS::WAFv2::WebACL", 0);
    assert.equal(web.WebACLId, undefined);
    assert.equal(admin.WebACLId, undefined);
  });

  const { plantilla, web, admin } = distribuciones({ ...CON_DOMINIO, waf: "1" });
  const [acl, ...otras] = propiedades(plantilla, "AWS::WAFv2::WebACL");
  const regla = (nombre: string) => acl.Rules.find((r: any) => r.Name === nombre);

  test("con -c waf=1, una sola lista de reglas para CloudFront, compartida por la web y administración", () => {
    assert.equal(otras.length, 0, "una sola: cada lista cuesta 5 USD al mes");
    assert.equal(acl.Scope, "CLOUDFRONT");
    assert.deepEqual(acl.DefaultAction, { Allow: {} });
    const idAcl = Object.keys(plantilla.findResources("AWS::WAFv2::WebACL"))[0];
    assert.deepEqual(web.WebACLId, { "Fn::GetAtt": [idAcl, "Arn"] });
    assert.deepEqual(admin.WebACLId, { "Fn::GetAtt": [idAcl, "Arn"] });
  });

  test("una tasa general por dirección IP, holgada para una oficina que comparte salida", () => {
    const general = regla("TasaGeneral");
    assert.ok(general, "falta la regla de tasa general");
    assert.equal(general.Statement.RateBasedStatement.AggregateKeyType, "IP");
    assert.equal(general.Statement.RateBasedStatement.Limit, 2000);
    assert.equal(general.Statement.RateBasedStatement.ScopeDownStatement, undefined);
  });

  test("el ingreso tiene la suya, más estricta: solo los POST a /api/v1/auth/login y a /entrar (administración)", () => {
    const ingreso = regla("TasaIngreso");
    assert.ok(ingreso, "falta la regla de tasa del ingreso");
    const tasa = ingreso.Statement.RateBasedStatement;
    assert.equal(tasa.AggregateKeyType, "IP");
    assert.equal(tasa.Limit, 20);
    assert.ok(tasa.Limit < regla("TasaGeneral").Statement.RateBasedStatement.Limit);
    const texto = JSON.stringify(tasa.ScopeDownStatement);
    assert.ok(texto.includes('"/api/v1/auth/login"') && texto.includes('"/entrar"') && texto.includes('"POST"'), texto);
    assert.ok(ingreso.Priority < regla("TasaGeneral").Priority, "el ingreso se evalúa antes que la general");
  });

  test("bloquea con 429 y el JSON de error del contrato (RATE_LIMITED): la web lo muestra como «ocupado»", () => {
    for (const nombre of ["TasaGeneral", "TasaIngreso"]) {
      const respuesta = regla(nombre).Action.Block.CustomResponse;
      assert.equal(respuesta.ResponseCode, 429, nombre);
      const cuerpo = acl.CustomResponseBodies[respuesta.CustomResponseBodyKey];
      assert.equal(cuerpo.ContentType, "APPLICATION_JSON");
      assert.equal(JSON.parse(cuerpo.Content).error.code, "RATE_LIMITED");
    }
  });
});

describe("cabecera secreta hacia la API (B1, la exige el frente A)", () => {
  const { web, admin } = distribuciones(CON_DOMINIO);
  const cabeceras = (o: any) => Object.fromEntries((o.OriginCustomHeaders ?? []).map((h: any) => [h.HeaderName, h.HeaderValue]));

  test("CloudFront añade X-Origen-CloudFront a lo que manda a la API, en la web y en administración", () => {
    for (const o of [origen(web, idApi(web)), origen(admin, admin.DefaultCacheBehavior.TargetOriginId)]) {
      const valor = JSON.stringify(cabeceras(o)["X-Origen-CloudFront"]);
      assert.ok(valor, "falta la cabecera");
      // El valor sale del secreto al desplegar: nunca queda escrito en la plantilla
      assert.match(valor, /\{\{resolve:secretsmanager:/);
      assert.match(valor, /:SecretString:ORIGEN_SECRETO::\}\}/);
    }
  });

  test("ni la función de la web ni los estáticos la reciben", () => {
    const idWeb = web.DefaultCacheBehavior.TargetOriginId;
    assert.equal(cabeceras(origen(web, idWeb))["X-Origen-CloudFront"], undefined);
    for (const o of web.Origins.filter((x: any) => x.S3OriginConfig)) assert.equal(o.OriginCustomHeaders, undefined);
  });
});

describe("concurrencia reservada de la API (B1)", () => {
  const { api } = sintetizar();
  const funciones = propiedades(api, "AWS::Lambda::Function");
  const laApi = funciones.find((f) => f.Environment?.Variables?.ANALIZADOR_FUNCION && !f.Environment?.Variables?.TAREAS);

  test("la API tiene 20: un pico o un ataque no se lleva la concurrencia de la cuenta (400)", () => {
    assert.equal(laApi.ReservedConcurrentExecutions, 20);
  });

  test("el guion de despliegue la conoce por la salida de la pila, para quitar la pausa con el mismo valor", () => {
    const salidas = api.findOutputs("ConcurrenciaReservada");
    assert.equal(Object.values(salidas)[0]?.Value, "20");
  });
});

describe("HSTS con subdominios (B1)", () => {
  const { plantilla, web, admin } = distribuciones(CON_DOMINIO);
  const politicas = plantilla.findResources("AWS::CloudFront::ResponseHeadersPolicy");
  const politica = (id: any) => politicas[id?.Ref]?.Properties.ResponseHeadersPolicyConfig;

  test("la web y sus estáticos: HSTS de un año con subdominios, más nosniff, marco propio y Referrer-Policy", () => {
    const estaticos = web.CacheBehaviors.find((c: any) => c.PathPattern === "/_next/static/*");
    for (const id of [web.DefaultCacheBehavior.ResponseHeadersPolicyId, estaticos.ResponseHeadersPolicyId]) {
      const seguridad = politica(id)?.SecurityHeadersConfig;
      assert.ok(seguridad, "falta la política propia de cabeceras");
      assert.equal(seguridad.StrictTransportSecurity.IncludeSubdomains, true);
      assert.ok(seguridad.StrictTransportSecurity.AccessControlMaxAgeSec >= 31536000);
      assert.equal(seguridad.ContentTypeOptions.Override, true);
      assert.equal(seguridad.FrameOptions.FrameOption, "SAMEORIGIN");
      assert.ok(seguridad.ReferrerPolicy);
    }
  });

  test("la API y administración: solo HSTS con subdominios; el resto de sus cabeceras las pone la aplicación", () => {
    const api = web.CacheBehaviors.find((c: any) => c.PathPattern === "/api/v1/*");
    for (const id of [api.ResponseHeadersPolicyId, admin.DefaultCacheBehavior.ResponseHeadersPolicyId]) {
      const config = politica(id);
      assert.ok(config, "falta la política de HSTS");
      assert.deepEqual(Object.keys(config.SecurityHeadersConfig), ["StrictTransportSecurity"]);
      assert.equal(config.SecurityHeadersConfig.StrictTransportSecurity.IncludeSubdomains, true);
      assert.equal(config.CustomHeadersConfig, undefined);
    }
  });
});
