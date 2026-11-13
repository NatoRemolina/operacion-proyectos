"""Recorrido de gastos sin claves: lectura guardada, validación, revisión, subidas hostiles."""
import json
import shutil
import subprocess

import pytest

from app import config, db
from app.main import _numero

BASE = {"proyecto_id": 1, "viajero_id": 1, "canal": "web"}


@pytest.fixture(autouse=True)
def _con_viaje(viaje_aprobado):
    """La regla exige que cada gasto pertenezca a un viaje aprobado: las cargas de este archivo van a ese viaje."""
    BASE["viaje_id"] = viaje_aprobado["id"]


def _subir(cliente, nombre, contenido, tipo="application/octet-stream"):
    return cliente.post("/gastos/cargar", data=BASE, files={"archivos": (nombre, contenido, tipo)},
                        headers={"X-Envio": "pagina"})


def _gasto(gid):
    return db.uno("select * from gastos where id=:i", i=gid)


def test_ejemplo_legible_se_aprueba_solo(cliente, ejemplos):
    r = _subir(cliente, "recibo.png", (ejemplos / "recibo_gasolina.png").read_bytes(), "image/png")
    g = _gasto(r.json()["gastos"][0])
    assert g["estado"] == "aprobado_auto" and g["total"] == 38.40 and g["extraido"]


def test_ejemplo_ilegible_va_a_revision(cliente, ejemplos):
    r = _subir(cliente, "x.png", (ejemplos / "recibo_parqueo_borroso.png").read_bytes(), "image/png")
    assert _gasto(r.json()["gastos"][0])["estado"] == "revision"


def test_duplicado_va_a_revision_y_se_aprueba_con_excepcion(cliente, ejemplos):
    foto = (ejemplos / "recibo_diner.png").read_bytes()
    _subir(cliente, "a.png", foto, "image/png")
    gid = _subir(cliente, "b.png", foto, "image/png").json()["gastos"][0]
    g = _gasto(gid)
    assert g["estado"] == "revision" and g["origen_dato"] == "reutilizado"   # no se paga otra lectura
    campos = dict(proyecto_id=1, viajero_id=1, comercio=g["comercio"], fecha=g["fecha"], categoria=g["categoria"],
                  total=str(g["total"]), moneda=g["moneda"])
    cliente.post(f"/gastos/{gid}", data={**campos, "accion": "aprobar"})
    assert _gasto(gid)["estado"] == "revision"                               # las reglas siguen bloqueando
    cliente.post(f"/gastos/{gid}", data={**campos, "accion": "excepcion", "motivo_excepcion": "corto"})
    assert _gasto(gid)["estado"] == "revision"                               # sin motivo real no pasa
    cliente.post(f"/gastos/{gid}", data={**campos, "accion": "excepcion", "motivo_excepcion": "Dos comidas del mismo día"})
    assert _gasto(gid)["estado"] == "aprobado"


def test_nombre_igual_a_un_ejemplo_no_hereda_su_lectura(cliente):
    """Un archivo cualquiera llamado como un ejemplo no debe aprobarse con los datos del ejemplo."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    g = _gasto(_subir(cliente, "recibo_diner.png", png, "image/png").json()["gastos"][0])
    assert g["estado"] == "revision" and g["total"] is None


def test_subidas_hostiles_se_rechazan(cliente):
    html = b"<html><script>alert(1)</script></html>"
    assert _subir(cliente, "recibo.html", html, "text/html").status_code == 400
    assert _subir(cliente, "foto.png", html, "image/png").status_code == 400          # tipo declarado falso
    assert _subir(cliente, "correo.eml", html, "message/rfc822").status_code == 400
    grande = b"\xff\xd8\xff" + b"0" * 4_600_000
    assert "MB" in _subir(cliente, "grande.jpg", grande, "image/jpeg").json()["errores"][0]


def test_nombre_con_rutas_no_escapa_del_almacen(cliente, ejemplos, tmp_path_factory):
    from app import config
    contenido = (ejemplos / "factura_hotel.pdf").read_bytes()
    r = _subir(cliente, "../../../../app/templates/base.html", contenido, "application/pdf")
    assert r.status_code == 200
    d = db.uno("select d.* from documentos d join gastos g on g.documento_id=d.id where g.id=:i", i=r.json()["gastos"][0])
    assert ".." not in d["ruta"] and "/" not in d["nombre"]
    assert (config.DIR_ARCHIVOS / d["ruta"].split(":", 1)[1]).is_file()


def test_soporte_se_sirve_aislado(cliente, ejemplos):
    gid = _subir(cliente, "c.eml", (ejemplos / "correo_tiquete.eml").read_bytes()).json()["gastos"][0]
    r = cliente.get(f"/gastos/{gid}/soporte")
    assert r.headers["x-content-type-options"] == "nosniff" and "sandbox" in r.headers["content-security-policy"]
    assert r.headers["content-type"].startswith("text/plain")


def test_numeros_con_coma_y_miles():
    assert _numero("1.234,56") == 1234.56 and _numero("1,234.56") == 1234.56
    assert _numero("23,50") == 23.5 and _numero("45.000") == 45000 and _numero("0.500") == 0.5
    assert _numero("abc") is None and _numero("") is None


def test_paginas_de_gastos_responden(cliente):
    for ruta in ("/gastos", "/gastos/cargar", "/gastos?estado=revision", "/proyectos/1", "/proyectos/1/exportar.csv", "/flujo", "/analitica"):
        assert cliente.get(ruta).status_code == 200, ruta


_DOBLE_DEL_NAVEGADOR = r"""
// Ejecuta el guion de la página de carga con lo mínimo del navegador: un lienzo que siempre comprime a 1000 bytes
const vm = require('vm'), fs = require('fs');
class File { constructor(partes, nombre, opciones) { this.name = nombre; this.type = opciones.type; this.size = partes[0].size; } }
const contexto = {
  File, window: {}, matchMedia: () => ({matches: false}),
  createImageBitmap: async () => ({width: 4000, height: 3000}),
  document: {
    getElementById: () => ({addEventListener() {}}), querySelector: () => null,
    createElement: () => ({getContext: () => ({drawImage() {}}), toBlob(listo, tipo) { listo({size: 1000, type: tipo}); }}),
  },
};
vm.createContext(contexto);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), contexto);
(async () => {
  const salida = {};
  for (const [nombre, tamano] of JSON.parse(process.argv[3])) {
    const r = await contexto.reducir({name: nombre, type: 'image/png', size: tamano});
    salida[nombre] = [r.name, r.type, r.size];
  }
  console.log(JSON.stringify(salida));
})();
"""


@pytest.mark.skipif(not shutil.which("node"), reason="hace falta node para ejecutar el guion de la página")
def test_la_pagina_de_carga_solo_reduce_las_fotos_que_superan_el_tope(piloto, tmp_path, ejemplos):
    """La lectura guardada de los ejemplos va por la huella del archivo: si la página recodifica una foto que ya cabe,
    deja de reconocerse. Solo se reduce lo que no cabe en el tope del servidor."""
    pagina = piloto.get("/gastos/cargar").text
    guion = next(s.split("</script>")[0] for s in pagina.split("<script>") if "function reducir" in s)
    (tmp_path / "pagina.js").write_text(guion)
    (tmp_path / "doble.js").write_text(_DOBLE_DEL_NAVEGADOR)
    ejemplo = (ejemplos / "recibo_diner.png").stat().st_size
    casos = [["recibo_diner.png", ejemplo], ["justo.png", config.MAX_BYTES_SOPORTE], ["celular.png", config.MAX_BYTES_SOPORTE + 1]]
    r = subprocess.run(["node", tmp_path / "doble.js", tmp_path / "pagina.js", json.dumps(casos)],  # noqa: S603, S607  guion fijo de esta prueba
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout)
    assert salida["recibo_diner.png"] == ["recibo_diner.png", "image/png", ejemplo]   # va tal cual
    assert salida["justo.png"] == ["justo.png", "image/png", config.MAX_BYTES_SOPORTE]
    assert salida["celular.png"] == ["celular.jpg", "image/jpeg", 1000]              # la foto grande sí se reduce
