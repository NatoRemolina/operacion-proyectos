import { App, Environment } from "aws-cdk-lib";
import { AppStack } from "./app-stack";
import { BaseStack } from "./base-stack";
import { WebStack } from "./web-stack";

/**
 * Una clave de contexto con espacios o que empieza con guion es una orden mal partida: por ejemplo "$CTX" sin partir
 * en zsh llega como `-c "dominio=… -c zonaId=…"`. Sin esta parada, la pila no vería el dominio y publicaría sin él.
 */
function comprobarContexto(app: App) {
  const malas = Object.keys(app.node.getAllContext()).filter((k) => /\s/.test(k) || k.startsWith("-"));
  if (malas.length) {
    throw new Error(`El contexto de CDK llegó mal partido (${malas.map((k) => JSON.stringify(k)).join(", ")}): `
      + "cada -c va con su clave=valor como argumento aparte (ver docs/despliegue.md).");
  }
}

/**
 * Tres pilas: lo que tiene estado (secreto, avisos), la API que se redespliega a menudo y la web delante de ella.
 * La usan `bin/app.ts` y las pruebas, para que ambas sinteticen exactamente lo mismo.
 */
export function crearPilas(app: App, entorno: Environment) {
  comprobarContexto(app);
  const base = new BaseStack(app, "OperacionBase", { env: entorno });
  const api = new AppStack(app, "OperacionApp", { env: entorno, secreto: base.secreto, avisos: base.avisos });
  const web = new WebStack(app, "OperacionWeb", { env: entorno, urlApi: api.url });
  return { base, api, web };
}
