import { describe, test } from "node:test";
import * as assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { sinVersionar } from "../lib/app-stack";

function carpeta(git: boolean) {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), "imagen-"));
  for (const d of ["app", "datos/respaldo", "web"]) fs.mkdirSync(path.join(raiz, d), { recursive: true });
  fs.writeFileSync(path.join(raiz, "app", "main.py"), "");
  fs.writeFileSync(path.join(raiz, "datos", "respaldo", "versionado.json"), "{}");
  fs.writeFileSync(path.join(raiz, "requirements.txt"), "fastapi\n");
  fs.writeFileSync(path.join(raiz, "Dockerfile"), "FROM python\n");
  if (git) {
    spawnSync("git", ["init", "-q"], { cwd: raiz });
    fs.writeFileSync(path.join(raiz, ".gitignore"), "datos/local.db\n");
    spawnSync("git", ["add", "."], { cwd: raiz });
    // Identidad solo para este commit de prueba: no toca la configuración de git
    spawnSync("git", ["-c", "user.name=prueba", "-c", "user.email=prueba@example.com", "commit", "-q", "-m", "inicio"], { cwd: raiz });
  }
  return raiz;
}

describe("lo que entraría en la imagen de la API sin estar versionado (H-71)", () => {
  test("señala lo nuevo de app/ y datos/, no lo ignorado ni lo de otras carpetas", () => {
    const raiz = carpeta(true);
    fs.writeFileSync(path.join(raiz, "datos", "respaldo", "vuelos_pagados.json"), "{}");
    fs.writeFileSync(path.join(raiz, "datos", "local.db"), "");
    fs.writeFileSync(path.join(raiz, "web", "borrador.ts"), "");
    assert.deepEqual(sinVersionar(raiz), ["datos/respaldo/vuelos_pagados.json"]);
  });

  test("señala lo versionado con cambios sin guardar, preparado o no", () => {
    const raiz = carpeta(true);
    fs.writeFileSync(path.join(raiz, "app", "main.py"), "cambio\n");
    fs.writeFileSync(path.join(raiz, "Dockerfile"), "FROM otra\n");
    spawnSync("git", ["add", "Dockerfile"], { cwd: raiz });
    fs.writeFileSync(path.join(raiz, "web", "borrador.ts"), "");
    assert.deepEqual(sinVersionar(raiz).sort(), ["Dockerfile", "app/main.py"]);
  });

  test("un archivo versionado que se borró también cuenta", () => {
    const raiz = carpeta(true);
    fs.rmSync(path.join(raiz, "requirements.txt"));
    assert.deepEqual(sinVersionar(raiz), ["requirements.txt"]);
  });

  test("una carpeta limpia no tiene nada que señalar", () => {
    assert.deepEqual(sinVersionar(carpeta(true)), []);
  });

  test("fuera de git no hay con qué comparar", () => {
    assert.deepEqual(sinVersionar(carpeta(false)), []);
  });
});
