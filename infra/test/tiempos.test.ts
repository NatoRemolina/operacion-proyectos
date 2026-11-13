import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { CON_DOMINIO, DOMINIO, propiedades, sintetizar } from "./ayuda";

const WEB = `software.${DOMINIO}`;

describe("tiempo máximo de la API detrás de CloudFront (H-70)", () => {
  const { web } = sintetizar(CON_DOMINIO);
  const configs = propiedades(web, "AWS::CloudFront::Distribution").map((p) => p.DistributionConfig);
  const origen = (d: any, id: string) => d.Origins.find((o: any) => o.Id === id);
  const webDist = configs.find((d) => d.Aliases[0] === WEB);
  const adminDist = configs.find((d) => d.Aliases[0] !== WEB);
  const idApi = webDist.CacheBehaviors.find((c: any) => c.PathPattern === "/api/v1/*").TargetOriginId;

  test("la API espera hasta 60 segundos en la web y en administración", () => {
    assert.equal(origen(webDist, idApi).CustomOriginConfig.OriginReadTimeout, 60);
    assert.equal(origen(adminDist, adminDist.DefaultCacheBehavior.TargetOriginId).CustomOriginConfig.OriginReadTimeout, 60);
  });

  test("un GET lento no se repite: el tablero de vuelos consulta el buscador pago dentro de un GET", () => {
    assert.equal(origen(webDist, idApi).ConnectionAttempts, 1);
    assert.equal(origen(adminDist, adminDist.DefaultCacheBehavior.TargetOriginId).ConnectionAttempts, 1);
  });

  test("la web conserva el plazo por omisión: sus páginas no hacen trabajo largo", () => {
    const funcionWeb = origen(webDist, webDist.DefaultCacheBehavior.TargetOriginId);
    assert.equal(funcionWeb.CustomOriginConfig.OriginReadTimeout ?? 30, 30);
  });
});
