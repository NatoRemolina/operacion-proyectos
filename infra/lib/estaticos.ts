import { DockerImage, ILocalBundling } from "aws-cdk-lib";
import { spawnSync } from "node:child_process";

/**
 * Saca `/_next/static` de la etapa de compilación de `web/Dockerfile`, con los mismos argumentos que la imagen
 * de la función. Así lo que sube al bucket es la misma compilación que sirve la función: Docker reutiliza esa
 * etapa al construir la imagen en el mismo equipo. Si alguna vez no coincidiera, CloudFront pide a la función
 * lo que falte en el bucket (grupo de orígenes en web-stack.ts).
 *
 * Solo corre cuando la pila se empaqueta (`cdk synth`, `cdk deploy`); `cdk ls` y las pruebas no compilan nada.
 */
export class EstaticosDeLaWeb implements ILocalBundling {
  constructor(private readonly dirWeb: string, private readonly argumentos: Record<string, string>) {}

  tryBundle(salida: string): boolean {
    const etiqueta = "operacion-web-estaticos:sintesis";
    const docker = (...args: string[]) => {
      const r = spawnSync("docker", args, { stdio: ["ignore", "pipe", "inherit"], encoding: "utf-8" });
      if (r.error || r.status !== 0) {
        throw new Error(`No se pudieron preparar los estáticos de la web (docker ${args[0]}). ¿Está Docker en marcha?`);
      }
      return (r.stdout ?? "").trim();
    };
    const construir = ["build", "--target", "compilacion", "--tag", etiqueta, "--quiet"];
    for (const [k, v] of Object.entries(this.argumentos)) construir.push("--build-arg", `${k}=${v}`);
    docker(...construir, this.dirWeb);
    const contenedor = docker("create", etiqueta);
    try {
      docker("cp", `${contenedor}:/app/.next/static/.`, salida);
    } finally {
      docker("rm", contenedor);
    }
    return true;
  }
}

/** Imagen exigida por CDK si el empaquetado local no corriera; nunca se usa porque `tryBundle` siempre responde. */
export const IMAGEN_DE_RESERVA = DockerImage.fromRegistry("public.ecr.aws/docker/library/alpine:3.20");
