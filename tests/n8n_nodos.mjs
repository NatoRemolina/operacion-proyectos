// Ejecuta con Node el código de los nodos Code del flujo exportado (docs/n8n/soportes-a-drive.json), con lo que n8n
// les daría: un aviso firmado de verdad, la salida de los nodos anteriores y los ayudantes de `this.helpers`.
// Lo corre tests/test_n8n.py; también sirve a mano: node tests/n8n_nodos.mjs docs/n8n/soportes-a-drive.json
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const flujo = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const codigo = (nombre) => flujo.nodes.find((n) => n.name === nombre).parameters.jsCode;
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const correr = (nombre, entorno, ctx) =>
  new AsyncFunction('$', '$input', '$vars', '$getWorkflowStaticData', 'require', 'Buffer', codigo(nombre))
    .call(ctx, entorno.$, entorno.$input, entorno.$vars ?? {}, entorno.$getWorkflowStaticData ?? (() => ({})), require, Buffer);

const SECRETO = 'secreto-de-prueba', BASE = 'https://software.ejemplo.test';
function aviso(extra = {}) {
  return {
    evento: 'gasto.registrado', entrega: `e-${Math.random()}`, gasto_id: 7, viaje: 'V-2026-0012', proyecto: 'Casa en Moab',
    persona: 'P-0002', fecha: '2026-12-09', comercio: '=HYPERLINK("x")', categoria: 'hotel', total: '119.00', moneda: 'USD',
    total_usd: '119.00', estado: 'aprobado_auto', alertas: [], enlace_gasto: `${BASE}/gastos/7`,
    lectura: {
      comercio: '=HYPERLINK("x")', subtotal: '100.00', impuesto: '19.00', propina: null, total: '119.00', numero_factura: '000123',
      id_fiscal: '900.123.456-7', lineas: [{ descripcion: 'Noche estándar', cantidad: '1.00', total: '100.00' }],
      confianza: '0.95', dudas: [], origen_dato: 'en vivo',
    },
    enlace_soporte: `${BASE}/api/v1/servicio/gastos/7/soporte?vence=1&firma=abc`, enlace_vence_en_segundos: 900, ...extra,
  };
}
function entrada(cuerpo, { secreto = SECRETO, crudo = true } = {}) {
  const bytes = Buffer.from(JSON.stringify(cuerpo), 'utf8');
  const t = Math.floor(Date.now() / 1000);
  const firma = createHmac('sha256', secreto).update(Buffer.concat([Buffer.from(`${t}.`), bytes])).digest('hex');
  const conf = { secreto_webhook: SECRETO, url_plataforma: BASE, carpeta_raiz: 'Inflight · Soportes',
    headers: { 'x-inflight-firma': `t=${t},v1=${firma}` }, body: cuerpo };
  return { conf, ctx: { helpers: { getBinaryDataBuffer: async () => (crudo ? bytes : null) } } };
}

const estatico = {};
const salidas = {};
const nodo = (n) => ({ first: () => salidas[n] });
async function verificar(cuerpo, opciones) {
  const { conf, ctx } = entrada(cuerpo, opciones);
  const [r] = await correr('Verificar firma', { $: nodo, $input: { first: () => ({ json: conf }) }, $getWorkflowStaticData: () => estatico }, ctx);
  return r.json;
}

// 1. Verificar firma: válido con el cuerpo crudo y con el JSON vuelto a serializar; deja pasar el aviso verificado
const cuerpo = aviso();
const valido = await verificar(cuerpo);
assert.equal(valido.estado, 'valida', valido.motivo);
assert.deepEqual(valido.aviso.lectura, cuerpo.lectura);
assert.equal((await verificar(aviso(), { crudo: false })).estado, 'valida');
assert.equal((await verificar(aviso(), { secreto: 'otro' })).estado, 'invalida');
assert.equal((await verificar(cuerpo)).estado, 'repetida');

// 2. Preparar lectura: el JSON del gasto y su lectura, con y sin el ayudante prepareBinaryData
salidas['Verificar firma'] = { json: valido };
salidas['Preparar archivo'] = { json: { carpeta: 'carpeta-mes' } };
for (const ayudante of [true, false]) {
  const ctx = { helpers: ayudante ? { prepareBinaryData: async (b, fileName, mimeType) => ({ data: b.toString('base64'), fileName, mimeType }) } : {} };
  const [pl] = await correr('Preparar lectura', { $: nodo, $input: { first: () => ({ json: { id: 'soporte-123' } }) } }, ctx);
  const contenido = JSON.parse(Buffer.from(pl.binary.data.data, 'base64').toString('utf8'));
  assert.equal(pl.json.carpeta, 'carpeta-mes');
  assert.ok(pl.json.nombre.endsWith(' · lectura.json') && pl.binary.data.mimeType === 'application/json');
  assert.equal(contenido.lectura.numero_factura, '000123');
  assert.equal(contenido.soporte_en_drive, 'https://drive.google.com/file/d/soporte-123/view');
  salidas['Preparar lectura'] = pl;
}

// 3. Fila de la hoja: identificadores como texto, importes como número, enlaces; tolera lectura nula y listas raras
const [fila] = await correr('Fila de la hoja', { $: nodo, $input: { first: () => ({ json: { id: 'lectura-456' } }) } }, {});
assert.equal(fila.json['N.º factura'], '000123');
assert.equal(fila.json['NIT o ID fiscal'], '900.123.456-7');
assert.equal(fila.json.Comercio, '=HYPERLINK("x")');   // la hoja escribe en modo RAW: no se vuelve fórmula
assert.equal(fila.json.Total, 119);
assert.equal(fila.json.Propina, '');
assert.equal(fila.json['Lectura en Drive'], 'https://drive.google.com/file/d/lectura-456/view');
assert.equal(fila.json['Gasto en la plataforma'], `${BASE}/gastos/7`);
salidas['Verificar firma'] = { json: { ...valido, aviso: aviso({ lectura: null, alertas: 'no es lista' }) } };
const [vacia] = await correr('Fila de la hoja', { $: nodo, $input: { first: () => ({ json: {} }) } }, {});
assert.equal(vacia.json['N.º factura'], '');
assert.equal(vacia.json.Alertas, '');
assert.equal(vacia.json['Lectura en Drive'], '');

// 4. La hoja escribe sin interpretar y n8n no guarda las ejecuciones exitosas
const hoja = flujo.nodes.find((n) => n.name === 'Agregar a la hoja').parameters;
assert.equal(hoja.options.cellFormat, 'RAW');
assert.deepEqual(hoja.columns.matchingColumns, ['Gasto']);
assert.equal(flujo.settings.saveDataSuccessExecution, 'none');
console.log('todo bien');
