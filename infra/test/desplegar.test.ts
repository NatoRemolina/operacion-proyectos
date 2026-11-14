import { before, describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/**
 * scripts/desplegar.zsh (B5): solo se publica desde la punta de dev. Corre en repositorios de git temporales, con
 * dobles de docker, aws, curl y npx en el PATH: ninguna prueba toca AWS ni la base.
 */
const GUION = path.join(__dirname, "..", "..", "scripts", "desplegar.zsh");
const hayZsh = spawnSync("zsh", ["-c", "true"]).status === 0;

function git(cwd: string, ...args: string[]) {
  const r = spawnSync("git", ["-c", "user.name=prueba", "-c", "user.email=prueba@example.com", ...args], { cwd, encoding: "utf-8" });
  assert.equal(r.status, 0, r.stderr);
  return r.stdout.trim();
}

/** Un repositorio con main, dev (un commit más) y una rama de trabajo (otro más). */
function repositorio(): string {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), "desplegar-"));
  git(raiz, "init", "-q", "-b", "main");
  fs.writeFileSync(path.join(raiz, "README.md"), "inicio\n");
  fs.mkdirSync(path.join(raiz, "infra"));
  fs.writeFileSync(path.join(raiz, "infra", ".gitkeep"), "");
  git(raiz, "add", ".");
  git(raiz, "commit", "-q", "-m", "inicio");
  git(raiz, "checkout", "-q", "-b", "dev");
  fs.writeFileSync(path.join(raiz, "README.md"), "dev\n");
  git(raiz, "commit", "-q", "-am", "en dev");
  git(raiz, "checkout", "-q", "-b", "worktree-frente");
  fs.writeFileSync(path.join(raiz, "README.md"), "frente\n");
  git(raiz, "commit", "-q", "-am", "en el frente");
  return raiz;
}

/** La carpeta principal falsa (.venv y .env.*) y los dobles de las herramientas, que anotan cada llamada. */
function entorno(opc: { npx?: string; directo?: string } = {}) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), "desplegar-entorno-"));
  const principal = path.join(base, "principal");
  const bin = path.join(base, "bin");
  fs.mkdirSync(path.join(principal, ".venv", "bin"), { recursive: true });
  fs.mkdirSync(bin);
  for (const f of [".env.supabase-publicada", ".env.produccion", ".env.supabase-pruebas"]) fs.writeFileSync(path.join(principal, f), "");
  const llamadas = path.join(base, "llamadas.txt");
  const doble = (nombre: string, cuerpo = "") =>
    fs.writeFileSync(path.join(bin, nombre), `#!/bin/sh\necho "${nombre} $*" >> "${llamadas}"\n${cuerpo}\nexit 0\n`, { mode: 0o755 });
  for (const n of ["python", "dotenv"]) doble(n);
  fs.renameSync(path.join(bin, "python"), path.join(principal, ".venv", "bin", "python"));
  fs.renameSync(path.join(bin, "dotenv"), path.join(principal, ".venv", "bin", "dotenv"));
  doble("docker");
  doble("npx", opc.npx ?? "");
  doble("npm");
  // Responde según la dirección: la API directa (sin CloudFront) da el código de opc.directo
  doble("curl", `case "$*" in
  *api.example.com*) echo "${opc.directo ?? "403"} " ;;
  *auth/me*) echo "401 " ;;
  *http://web.example.com/entrar*) echo "301 https://web.example.com/entrar" ;;
  *admin/viajes*) echo "302 https://web.example.com/viajes" ;;
  *) echo "200 " ;;
esac`);
  doble("aws", `case "$1 $2" in
  "sts get-caller-identity") echo 000000000000 ;;
  "configure export-credentials") echo "export AWS_ACCESS_KEY_ID=AKIAFALSA AWS_SECRET_ACCESS_KEY=no-es-real" ;;
  "cloudformation describe-stacks") case "$*" in *FuncionTareas*) echo OperacionApp-Tareas ;; *Funcion*) echo OperacionApp-Web ;; *Concurrencia*) echo 20 ;; *UrlWeb*) echo https://web.example.com ;; *UrlAdmin*) echo https://admin.example.com ;; *"=='Url'"*) echo https://api.example.com/ ;; *) echo None ;; esac ;;
  "cloudwatch describe-alarms") echo OperacionApp-RechazosAnalizador ;;
esac`);
  const respaldos = path.join(base, "respaldos");
  const env = {
    ...process.env, PATH: `${bin}:${process.env.PATH}`, PRINCIPAL: principal, RESPALDOS: respaldos,
    CORREO_AVISOS: "avisos@example.com", AWS_PROFILE: "operacion",
  };
  return { env, llamadas, respaldos };
}

function desplegar(cwd: string, args: string[] = ["--ensayo"], input = "", opc: { npx?: string; directo?: string } = {}) {
  const { env, llamadas, respaldos } = entorno(opc);
  const r = spawnSync("zsh", [GUION, ...args], { cwd, env, encoding: "utf-8", input });
  const anotadas = fs.existsSync(llamadas) ? fs.readFileSync(llamadas, "utf-8") : "";
  return { codigo: r.status, salida: `${r.stdout}${r.stderr}`, llamadas: anotadas, respaldos };
}

describe("guion de despliegue: solo desde la punta de dev (B5)", { skip: !hayZsh && "sin zsh en este equipo" }, () => {
  let raiz: string;
  before(() => {
    raiz = repositorio();
  });

  test("desde otra rama se rechaza con un mensaje claro y sin tocar nada", () => {
    git(raiz, "checkout", "-q", "worktree-frente");
    const r = desplegar(raiz);
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /Solo se despliega desde la punta de dev/);
    assert.match(r.salida, /worktree-frente/);
    assert.equal(r.llamadas, "", "no llamó a docker, aws ni a nada más");
  });

  test("un commit anterior de dev, aunque esté en su historia, también se rechaza", () => {
    git(raiz, "checkout", "-q", "--detach", "dev~1");
    const r = desplegar(raiz);
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /Solo se despliega desde la punta de dev/);
  });

  test("main tampoco: la regla es dev", () => {
    git(raiz, "checkout", "-q", "main");
    const r = desplegar(raiz);
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /Solo se despliega desde la punta de dev/);
  });

  test("en la punta de dev pero con cambios sin guardar, se rechaza", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    fs.writeFileSync(path.join(raiz, "README.md"), "cambio sin guardar\n");
    const r = desplegar(raiz);
    git(raiz, "checkout", "-q", "--", "README.md");
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /cambios sin guardar/);
  });

  test("sin rama dev no hay de dónde publicar", () => {
    const otro = repositorio();
    git(otro, "checkout", "-q", "main");
    git(otro, "branch", "-q", "-D", "dev");
    const r = desplegar(otro);
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /No existe la rama dev/);
  });

  test("en la punta de dev, el ensayo comprueba, muestra el plan y no escribe nada", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const r = desplegar(raiz);
    assert.equal(r.codigo, 0, r.salida);
    assert.match(r.salida, /es la punta de dev/);
    for (const paso of ["put-function-concurrency", "datos.respaldar respaldar", "datos.semilla", "datos.comprobar_supabase",
      "poblar_secreto.py", "cdk diff", "cdk deploy OperacionApp", "cdk deploy OperacionWeb", "--reserved-concurrent-executions 20"]) {
      assert.match(r.salida, new RegExp(`\\[ensayo\\].*${paso.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`), `el plan no muestra ${paso}`);
    }
    // Solo lecturas: Docker, la identidad, las credenciales para boto3 y las salidas de las pilas
    const escrituras = r.llamadas.split("\n").filter((l) => /put-|delete-|disable-|enable-|cdk |respaldar|semilla|poblar/.test(l));
    assert.deepEqual(escrituras, []);
    assert.doesNotMatch(r.salida, /no-es-real|AKIAFALSA/, "las credenciales no se imprimen");
  });

  test("todo queda registrado en la carpeta de respaldos", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const r = desplegar(raiz);
    const registros = fs.readdirSync(r.respaldos);
    assert.equal(registros.length, 1);
    assert.match(registros[0]!, /^despliegue_.*_ensayo\.log$/);
    const texto = fs.readFileSync(path.join(r.respaldos, registros[0]!), "utf-8");
    assert.match(texto, /Comprobaciones/);
  });

  test("sin el correo de las alarmas no sigue (CloudFormation borraría la suscripción)", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const { env } = entorno();
    const r = spawnSync("zsh", [GUION, "--ensayo"], { cwd: raiz, env: { ...env, CORREO_AVISOS: "" }, encoding: "utf-8" });
    assert.notEqual(r.status, 0);
    assert.match(`${r.stdout}${r.stderr}`, /CORREO_AVISOS/);
  });

  test("una corrida real, sin --ensayo, pausa, despliega y devuelve la concurrencia", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const r = desplegar(raiz, [], "si\nsi\nsi\nsi\n");
    assert.equal(r.codigo, 0, r.salida);
    assert.match(r.salida, /== 2\. Pausa/);
    assert.match(r.salida, /Fin de la pausa/);
    const l = r.llamadas.split("\n");
    const pausa = l.findIndex((x) => /put-function-concurrency .* 0$/.test(x));
    const respaldo = l.findIndex((x) => /datos\.respaldar/.test(x));
    const web = l.findIndex((x) => /cdk deploy OperacionWeb/.test(x));
    const devuelta = l.findIndex((x, i) => i > web && /put-function-concurrency .* 20$/.test(x));
    assert.ok(pausa >= 0 && pausa < respaldo, "la pausa va antes del respaldo");
    assert.ok(web >= 0 && devuelta > web, "la concurrencia se devuelve después de desplegar la web");
  });

  test("si falla una orden con la API en pausa, avisa cómo quitar la pausa y sale con error", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const r = desplegar(raiz, [], "si\nsi\nsi\nsi\n", { npx: 'case "$*" in *"cdk deploy OperacionBase"*) exit 1 ;; esac' });
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /siguen en pausa/);
    assert.match(r.salida, /put-function-concurrency --function-name OperacionApp-Web --reserved-concurrent-executions 20/);
    assert.match(r.salida, /enable-alarm-actions --alarm-names OperacionApp-RechazosAnalizador/);
  });

  test("si falla la pausa de Tareas, también avisa", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const { env } = entorno();
    const bin = env.PATH!.split(":")[0]!;
    const aws = fs.readFileSync(path.join(bin, "aws"), "utf-8").replace(
      'case "$1 $2" in', 'case "$*" in *"put-function-concurrency"*OperacionApp-Tareas*) exit 1 ;; esac\ncase "$1 $2" in');
    fs.writeFileSync(path.join(bin, "aws"), aws, { mode: 0o755 });
    const r = spawnSync("zsh", [GUION], { cwd: raiz, env, encoding: "utf-8", input: "si\nsi\nsi\nsi\n" });
    assert.notEqual(r.status, 0);
    assert.match(`${r.stdout}${r.stderr}`, /siguen en pausa/);
  });

  test("con dev local detrás de origin/dev pide confirmación y no sigue si no se escribe «si»", () => {
    const otro = repositorio();
    git(otro, "checkout", "-q", "--detach", "dev");
    git(otro, "update-ref", "refs/remotes/origin/dev", git(otro, "rev-parse", "worktree-frente"));
    const r = desplegar(otro, [], "no\n");
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /dev local está detrás de origin\/dev/);
    assert.equal(r.llamadas.includes("put-function-concurrency"), false);
  });

  test("si la función acepta peticiones directas (200 sin CloudFront), el guion termina con error y lo dice", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const r = desplegar(raiz, [], "si\nsi\nsi\nsi\n", { directo: "200" });
    assert.notEqual(r.codigo, 0);
    assert.match(r.salida, /La función acepta peticiones directas: revisa ORIGEN_SECRETO en el secreto y vuelve a desplegar OperacionApp/);
  });

  test("si la función rechaza lo directo con 403, la comprobación pasa", () => {
    git(raiz, "checkout", "-q", "--detach", "dev");
    const r = desplegar(raiz, [], "si\nsi\nsi\nsi\n", { directo: "403" });
    assert.equal(r.codigo, 0, r.salida);
    assert.match(r.salida, /✓ La dirección directa de la API no atiende sin CloudFront: 403/);
  });
});
