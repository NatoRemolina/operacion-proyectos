"""Errores y callejones sin salida de la plataforma, corregidos. Cada prueba fija una corrección."""
import re

from app import db
from app.servicios import costo, validacion

FORM = dict(proyecto_id=1, viajero_id=2, origen="Miami (MIA)", destino="las vegas", ciudad="", ida="2026-12-08",
            regreso="2026-12-11", llegar_antes="2026-12-08T18:00", baterias_n=4, baterias_wh=77, maleta="on",
            prob_cambio=25, carro_dia=65)


def _sid(r):
    return int(r.headers["location"].rsplit("/", 1)[1])


def test_un_piloto_cotiza_siempre_su_propio_viaje(piloto):
    """Aunque el formulario traiga otro viajero (el primero de la lista), el titular es quien cotiza."""
    assert 'name="viajero_id" value="1"' in piloto.get("/viajes/nuevo").text and "registrar un viajero nuevo" not in piloto.get("/viajes/nuevo").text
    sid = _sid(piloto.post("/viajes", data={**FORM, "viajero_id": 2, "viajero_nuevo": "Alguien"}, follow_redirects=False))
    assert db.uno("select viajero_id from solicitudes where id=:i", i=sid)["viajero_id"] == 1
    assert not db.uno("select id from viajeros where nombre='Alguien'")


def test_una_regla_numerica_mal_escrita_no_se_guarda_ni_tumba_nada(cliente):
    tasa = db.uno("select * from reglas where clave='tasa_EUR_USD'")
    r = cliente.post(f"/reglas/{tasa['id']}", data={"valor": "1,10"}, follow_redirects=False)
    assert "guardada" in r.headers["location"] and db.uno("select valor from reglas where id=:i", i=tasa["id"])["valor"] == "1.10"
    r = cliente.post(f"/reglas/{tasa['id']}", data={"valor": "uno coma diez"}, follow_redirects=False)
    assert "No+se+guard" in r.headers["location"] or "No%20se%20guard" in r.headers["location"]
    assert db.uno("select valor from reglas where id=:i", i=tasa["id"])["valor"] == "1.10"
    cliente.post(f"/reglas/{tasa['id']}", data={"valor": tasa["valor"]})
    # Aunque un valor dañado llegue a la base por otra vía, convertir importes no se cae
    assert validacion.a_usd(10, "EUR", {("supuesto", "", "", "tasa_EUR_USD"): {"valor": "1,08"}}) is None
    assert costo._numero({"valor": "80 USD"}, 80.0) == 80.0


def test_sesion_vencida_se_explica_y_conserva_el_destino(anonimo, ejemplos):
    r = anonimo.get("/gastos/cargar", follow_redirects=False)
    assert r.headers["location"] == "/entrar?siguiente=/gastos/cargar"
    r = anonimo.post("/gastos/cargar", headers={"X-Envio": "pagina"}, data={"canal": "web"},
                     files={"archivos": ("r.png", (ejemplos / "recibo_diner.png").read_bytes(), "image/png")})
    assert r.status_code == 401 and "sesión se cerró" in r.json()["errores"][0]
    r = anonimo.post("/entrar", data={"correo": "piloto@demo.local", "clave": "demo-piloto-2026", "siguiente": "/gastos/cargar"},
                     follow_redirects=False)
    assert r.headers["location"] == "/gastos/cargar"
    anonimo.post("/salir")
    r = anonimo.post("/entrar", data={"correo": "piloto@demo.local", "clave": "demo-piloto-2026", "siguiente": "//sitio-ajeno.example"},
                     follow_redirects=False)
    assert r.headers["location"] == "/"   # nunca a otro sitio


def test_la_decision_solo_se_ofrece_a_quien_puede_decidir(gestor, piloto, viaje_aprobado):
    sid = viaje_aprobado["solicitud_id"]
    assert "Guardar decisión y enviar a aprobación" not in gestor.get(f"/viajes/{sid}").text
    assert "ya está aprobado" in piloto.get(f"/viajes/{sid}").text   # el viaje del piloto ya tiene el presupuesto aprobado


def test_decidir_dos_veces_lo_mismo_no_duplica(piloto):
    sid = _sid(piloto.post("/viajes", data=FORM, follow_redirects=False))   # ruta con respuesta guardada: siempre hay vuelos
    vuelo = re.search(r'name="vuelo_id" value="(\d+)"', piloto.get(f"/viajes/{sid}").text)
    assert vuelo
    for _ in range(2):
        piloto.post(f"/viajes/{sid}/decidir", data={"vuelo_id": vuelo[1]})
    assert db.uno("select count(*) n from decisiones where solicitud_id=:s", s=sid)["n"] == 1


def test_un_viaje_rechazado_lleva_a_cambiar_la_decision(cliente, piloto, nuevo_viaje):
    v = nuevo_viaje(aprobar=False)
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "rechazar", "motivo": "Hay una opción más barata"})
    detalle = piloto.get(f"/viaje/{v['id']}").text
    assert "no aprobó este presupuesto" in detalle and f'href="/viajes/{v["solicitud_id"]}"' in detalle
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "reabrir"})
    cliente.post(f"/admin/viajes/{v['id']}", data={"accion": "aprobar"})


def test_el_gestor_abre_solo_el_tablero_de_sus_proyectos(gestor):
    assert gestor.get("/proyectos/1").status_code == 200 and gestor.get("/proyectos/1/exportar.csv").status_code == 200
    assert gestor.get("/proyectos/2").status_code == 404
    assert 'href="/proyectos/1"' in gestor.get("/").text   # su inicio le muestra sus proyectos


def test_desactivar_dos_veces_no_reactiva_la_cuenta(cliente):
    cliente.post("/admin/usuarios", data={"correo": "doble@demo.local", "nombre": "Doble Envío", "rol": "piloto", "clave": "clave-doble-1"})
    uid = db.uno("select id from usuarios where correo='doble@demo.local'")["id"]
    for _ in range(2):
        cliente.post(f"/admin/usuarios/{uid}", data={"accion": "estado", "activo": "0"})
    assert db.uno("select activo from usuarios where id=:i", i=uid)["activo"] == 0


def test_el_tablero_que_se_actualiza_solo_no_mantiene_viva_la_sesion(cliente):
    token = cliente.cookies.get("sesion")
    from app.servicios import acceso
    antes = db.uno("select ultima from sesiones where huella=:h", h=acceso.huella(token))["ultima"]
    db.ejecutar("update sesiones set ultima='2000-01-01 00:00:00' where huella=:h", h=acceso.huella(token))
    assert acceso.usuario_de(token, tocar=False) is None   # 2000 está fuera de la inactividad: no se reaviva
    db.ejecutar("update sesiones set ultima=:u where huella=:h", u=antes, h=acceso.huella(token))
