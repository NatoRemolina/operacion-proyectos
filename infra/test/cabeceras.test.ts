import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { CACHE_LARGA, CON_DOMINIO, DOMINIO, TODO_EL_VISITANTE, propiedades, sintetizar } from "./ayuda";

const WEB = `software.${DOMINIO}`;

function configs(contexto: Record<string, string>) {
  const { web } = sintetizar(contexto);
  const ds = propiedades(web, "AWS::CloudFront::Distribution").map((p) => p.DistributionConfig);
  return { web: ds.find((d) => d.Aliases[0] === WEB), admin: ds.find((d) => d.Aliases[0] !== WEB) };
}

describe("cabeceras que CloudFront reenvía (H-69)", () => {
  const { web, admin } = configs(CON_DOMINIO);
  const ruta = (patron: string) => web.CacheBehaviors.find((c: any) => c.PathPattern === patron);

  test("/api/v1/* recibe cookies y todas las cabeceras del visitante menos Host", () => {
    // Origin, Sec-Fetch-Site, X-CSRF-Token, Idempotency-Key y la cookie de sesión llegan a la API
    assert.equal(ruta("/api/v1/*").OriginRequestPolicyId, TODO_EL_VISITANTE);
  });

  test("administración también: sus formularios dependen de Sec-Fetch-Site y de la cookie", () => {
    assert.equal(admin.DefaultCacheBehavior.OriginRequestPolicyId, TODO_EL_VISITANTE);
  });

  test("la web recibe la consulta y las cabeceras de navegación de Next", () => {
    assert.equal(web.DefaultCacheBehavior.OriginRequestPolicyId, TODO_EL_VISITANTE);
  });

  test("los estáticos no reciben cookies ni cabeceras del visitante", () => {
    assert.equal(ruta("/_next/static/*").OriginRequestPolicyId, undefined);
    assert.equal(ruta("/_next/static/*").CachePolicyId, CACHE_LARGA);
  });
});

describe("ORIGENES_WEB en la API", () => {
  const variables = (contexto: Record<string, string>) => {
    const { api } = sintetizar(contexto);
    const [funcion] = propiedades(api, "AWS::Lambda::Function").filter((f) => f.PackageType === "Image");
    return funcion.Environment.Variables;
  };

  test("con dominio, la API acepta escrituras desde la web nueva", () => {
    assert.equal(variables(CON_DOMINIO).ORIGENES_WEB, `https://${WEB}`);
  });

  test("sin dominio no se fija aquí: va en el secreto con la dirección de CloudFront", () => {
    assert.equal(variables({}).ORIGENES_WEB, undefined);
  });
});
