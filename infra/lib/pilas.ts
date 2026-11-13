import { App, Environment } from "aws-cdk-lib";
import { AppStack } from "./app-stack";
import { BaseStack } from "./base-stack";
import { WebStack } from "./web-stack";

/**
 * Tres pilas: lo que tiene estado (secreto, avisos), la API que se redespliega a menudo y la web delante de ella.
 * La usan `bin/app.ts` y las pruebas, para que ambas sinteticen exactamente lo mismo.
 */
export function crearPilas(app: App, entorno: Environment) {
  const base = new BaseStack(app, "OperacionBase", { env: entorno });
  const api = new AppStack(app, "OperacionApp", { env: entorno, secreto: base.secreto, avisos: base.avisos });
  const web = new WebStack(app, "OperacionWeb", { env: entorno, urlApi: api.url });
  return { base, api, web };
}
