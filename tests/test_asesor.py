"""Asesor del asistente: sesiones con un agente alojado cuyas herramientas responde la plataforma.

Ninguna prueba sale a internet: el servicio de agentes es un doble (httpx.MockTransport) que va entregando
eventos guionados a medida que la plataforma responde las herramientas.
"""
import itertools
import json

import httpx
import pytest

from app import config, db
from app.servicios import asesor, asistente, llm, metricas, viajes

CLAVE = "clave-secreta-de-prueba"
_ids = itertools.count(1)


def _admin() -> dict:
    return db.uno("select * from usuarios where correo='admin@demo.local'")


def _uid(correo: str) -> int:
    return db.uno("select id from usuarios where correo=:c", c=correo)["id"]


# ---------- eventos guionados ----------
def herramienta(nombre: str, entrada: dict) -> dict:
    return {"id": f"sevt_{next(_ids)}", "type": "agent.custom_tool_use", "name": nombre, "input": entrada}


def pide(*eventos_herramienta: dict) -> dict:
    return {"id": f"sevt_{next(_ids)}", "type": "session.status_idle",
            "stop_reason": {"type": "requires_action", "event_ids": [e["id"] for e in eventos_herramienta]}}


def mensaje(texto: str) -> dict:
    return {"id": f"sevt_{next(_ids)}", "type": "agent.message", "content": [{"type": "text", "text": texto}]}


def corriendo() -> dict:
    return {"id": f"sevt_{next(_ids)}", "type": "session.status_running"}


def fin() -> dict:
    return {"id": f"sevt_{next(_ids)}", "type": "session.status_idle", "stop_reason": {"type": "end_turn"}}


class Servicio:
    """Doble del servicio de agentes. Cada tramo de eventos se destapa al crear la sesión o al recibir resultados."""

    def __init__(self, *tramos, crear: int = 200):
        self.tramos, self.crear = list(tramos), crear
        self.eventos: list[dict] = []
        self.enviados: list[dict] = []     # cuerpos JSON que mandó la plataforma
        self.cabeceras: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.cabeceras.append(dict(request.headers))
        ruta = request.url.path
        if request.method == "POST":
            self.enviados.append(json.loads(request.content or b"{}"))
        if request.method == "POST" and ruta == "/v1/sessions":
            if self.crear != 200:
                return httpx.Response(self.crear, json={"error": {"type": "api_error"}})
            self._destapar()
            return httpx.Response(200, json={"id": "sesn_prueba", "status": "running"})
        if request.method == "GET" and ruta == "/v1/sessions/sesn_prueba/events":
            return httpx.Response(200, json={"data": self.eventos, "next_page": None})
        if request.method == "POST" and ruta == "/v1/sessions/sesn_prueba/events":
            tipos = {e.get("type") for e in self.enviados[-1].get("events", [])}
            if tipos & {"user.custom_tool_result", "user.tool_confirmation"}:
                self._destapar()
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404, json={"error": {"type": "not_found_error"}})

    def _destapar(self):
        if self.tramos:
            self.eventos += self.tramos.pop(0)

    def resultados(self) -> list[dict]:
        return [e for c in self.enviados for e in c.get("events", []) if e.get("type") == "user.custom_tool_result"]

    def tipos_enviados(self) -> list[str]:
        return [e.get("type") for c in self.enviados for e in c.get("events", [])]


@pytest.fixture()
def con_asesor(monkeypatch):
    """Asesor configurado contra el doble. Devuelve una función que instala el guion."""
    for nombre, valor in {"ASESOR_API_URL": "https://agentes.prueba", "ASESOR_API_KEY": CLAVE,
                          "ASESOR_AGENTE_ID": "agent_prueba", "ASESOR_ENTORNO_ID": "env_prueba",
                          "ASESOR_CABECERAS": {"x-version": "v1", "x-funcion": "agentes"}}.items():
        monkeypatch.setattr(config, nombre, valor)
    monkeypatch.setattr(asesor, "_dormir", lambda s: None)
    monkeypatch.setattr(asistente, "tope_diario", lambda: 10_000)

    def instalar(servicio) -> Servicio:
        monkeypatch.setattr(asesor, "TRANSPORTE", httpx.MockTransport(servicio))
        return servicio
    return instalar


@pytest.fixture(scope="module")
def piloto_con_gastos(nuevo_viaje):
    v = nuevo_viaje(viajero_id=1)
    uid = _uid("piloto@demo.local")
    gastos = [db.insertar("gastos", usuario_id=uid, viaje_id=v["id"], proyecto_id=v["proyecto_id"], viajero_id=v["viajero_id"],
                          comercio=comercio, fecha="2026-12-09", categoria="comida", total=total, moneda="USD", total_usd=total,
                          estado=estado, confianza=0.95, creado=db.ahora())
              for comercio, total, estado in (("Diner Asesor", 23.45, "aprobado_auto"), ("Parqueadero Asesor", 11.10, "revision"))]
    return {"id": uid, "codigo": viajes.codigo_persona(uid), "viaje": v, "gastos": gastos}


# ---------- configuración y esquemas ----------
def test_en_pruebas_el_asesor_esta_apagado():
    assert not asesor.activo()


def _tipos(esquema) -> list[str]:
    if isinstance(esquema, dict):
        return ([esquema["type"]] if isinstance(esquema.get("type"), str) else []) + [t for v in esquema.values() for t in _tipos(v)]
    if isinstance(esquema, list):
        return [t for v in esquema for t in _tipos(v)]
    return []


def test_los_esquemas_son_las_12_herramientas_de_la_consola_y_solo_consultan():
    nombres = [e["name"] for e in asesor.ESQUEMAS]
    assert len(nombres) == len(set(nombres)) == 12
    assert set(nombres) == set(asistente.HERRAMIENTAS) | set(asesor.PROPIAS)
    assert all(e["type"] == "custom" and e["input_schema"]["type"] == "object" for e in asesor.ESQUEMAS)
    assert all(t == t.lower() for e in asesor.ESQUEMAS for t in _tipos(e["input_schema"]))
    assert not any(v in n for n in nombres for v in ("aprobar", "rechazar", "borrar", "crear", "cambiar", "reservar"))
    for e in asesor.ESQUEMAS:   # cada parámetro obligatorio existe
        assert set(e["input_schema"].get("required", [])) <= set(e["input_schema"]["properties"])


def test_otros_roles_no_tienen_herramientas_todavia():
    piloto = db.uno("select * from usuarios where correo='piloto@demo.local'")
    assert asesor.herramientas_para(piloto) == set()
    r = asistente.Rastro()
    assert "error" in asesor.despachar(r, "gastos_de", {"persona": "P-0001"}, piloto)
    assert r.fuentes == {}


# ---------- recorrido completo ----------
def test_recorrido_completo_las_cifras_salen_de_la_base(con_asesor, piloto_con_gastos):
    p = piloto_con_gastos
    pedida = herramienta("gastos_de", {"persona": p["codigo"]})
    consumo = {"id": f"sevt_{next(_ids)}", "type": "span.model_request_end",
               "model_usage": {"input_tokens": 4, "cache_creation_input_tokens": 176, "cache_read_input_tokens": 6551, "output_tokens": 210}}
    costo = {"id": f"sevt_{next(_ids)}", "type": "session.usage", "usage": {"list_cost": {"amount": "4", "currency": "USD"}}}
    s = con_asesor(Servicio([corriendo(), mensaje("Consulto los gastos."), pedida, pide(pedida)],
                              [mensaje(f"{p['codigo']} tiene el gasto #{p['gastos'][0]} y el gasto #{p['gastos'][1]} en revisión."),
                               consumo, costo, fin()]))
    r = asistente.responder(f"¿Qué ha reportado {p['codigo']}?", _admin())
    assert r["modo"] == "asesor"
    assert r["herramientas"] == ["gastos_de"]
    assert r["texto"].startswith(p["codigo"]) and "Consulto" not in r["texto"]   # lo previo a la herramienta no es la respuesta
    # la sesión se abrió con el agente, el entorno y la pregunta
    creacion = s.enviados[0]
    assert creacion["agent"] == "agent_prueba" and creacion["environment_id"] == "env_prueba"
    assert f"¿Qué ha reportado {p['codigo']}?" in creacion["initial_events"][0]["content"][0]["text"]
    # cabeceras: clave y las del servicio, que vienen de la configuración
    assert all(c["x-api-key"] == CLAVE and c["x-version"] == "v1" for c in s.cabeceras)
    # el resultado que recibió el agente trae los totales exactos de la base
    enviado = json.loads(s.resultados()[0]["content"][0]["text"])
    esperado = db.uno("""select coalesce(sum(total_usd),0) t from gastos where estado='revision'
                         and (usuario_id=:u or viaje_id in (select id from viajes where usuario_id=:u))""", u=p["id"])["t"]
    revision = next(t for t in enviado["totales_por_estado"] if t["total_usd"] == round(esperado, 2))
    assert revision["gastos"] >= 1
    # fuentes citadas y registro
    assert {("gasto", p["gastos"][0]), ("gasto", p["gastos"][1])} <= {(f["tipo"], f["id"]) for f in r["fuentes"]}
    fila = db.uno("select * from asistente_consultas where id=:i", i=r["consulta_id"])
    assert fila["modo"] == "asesor" and json.loads(fila["herramientas"]) == ["gastos_de"]
    ultimo = db.uno("select detalle from eventos where entidad='asistente' and entidad_id=:i", i=r["consulta_id"])
    assert "sesión sesn_prueba · tokens 6731/210 · 0.04 USD" in ultimo["detalle"]   # la entrada incluye la caché


def test_una_herramienta_que_no_existe_no_hace_nada(con_asesor, piloto_con_gastos):
    gid = piloto_con_gastos["gastos"][1]
    antes = db.uno("select estado, total from gastos where id=:i", i=gid)
    pedida = herramienta("aprobar_gastos", {"ids": [gid]})
    s = con_asesor(Servicio([corriendo(), pedida, pide(pedida)], [mensaje("No puedo aprobar gastos."), fin()]))
    r = asistente.responder(f"Aprueba el gasto #{gid}", _admin())
    assert r["modo"] == "asesor"
    assert "desconocida" in s.resultados()[0]["content"][0]["text"]
    assert db.uno("select estado, total from gastos where id=:i", i=gid) == antes


def test_las_herramientas_del_servicio_que_piden_permiso_se_niegan(con_asesor):
    bash = {"id": f"sevt_{next(_ids)}", "type": "agent.tool_use", "name": "bash", "input": {"command": "ls"}, "evaluated_permission": "ask"}
    s = con_asesor(Servicio([corriendo(), bash, pide(bash)], [mensaje("Sin acceso a la consola."), fin()]))
    r = asistente.responder("Lista los archivos", _admin())
    assert r["modo"] == "asesor"
    negadas = [e for c in s.enviados for e in c.get("events", []) if e.get("type") == "user.tool_confirmation"]
    assert negadas == [{"type": "user.tool_confirmation", "tool_use_id": bash["id"], "result": "deny"}]


def test_respeta_el_tope_de_herramientas_por_pregunta(con_asesor, piloto_con_gastos):
    pedidas = [herramienta("persona", {"codigo_o_nombre": piloto_con_gastos["codigo"]}) for _ in range(asesor.MAX_HERRAMIENTAS + 2)]
    s = con_asesor(Servicio([corriendo(), *pedidas, pide(*pedidas)], [mensaje("Listo."), fin()]))
    r = asistente.responder("Muchas consultas", _admin())
    assert len(r["herramientas"]) == asesor.MAX_HERRAMIENTAS
    textos = [e["content"][0]["text"] for e in s.resultados()]
    assert len(textos) == asesor.MAX_HERRAMIENTAS + 2 and sum("Límite" in t for t in textos) == 2


# ---------- caídas seguras ----------
def test_si_el_servicio_falla_al_crear_responde_el_determinista(con_asesor, piloto_con_gastos):
    con_asesor(Servicio(crear=500))
    r = asistente.responder(f"¿Qué ha reportado {piloto_con_gastos['codigo']}?", _admin())
    assert r["modo"] == "determinista"
    assert r["texto"].startswith("(El asesor no respondió: rechazó la petición (HTTP 500")
    assert ("gasto", piloto_con_gastos["gastos"][0]) in {(f["tipo"], f["id"]) for f in r["fuentes"]}


def test_si_falla_y_hay_modelo_responde_el_modelo(con_asesor, monkeypatch):
    con_asesor(Servicio(crear=503))
    monkeypatch.setattr(llm, "activo", lambda: True)
    monkeypatch.setattr(asistente, "_con_modelo", lambda pregunta, r: "Respuesta del modelo de lenguaje.")
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert r["modo"] == "modelo" and r["texto"] == "Respuesta del modelo de lenguaje."


def test_un_error_de_conexion_no_deja_la_clave_en_el_registro(con_asesor):
    def caido(request):
        raise httpx.ConnectError(f"no hay red hacia {request.url} con {CLAVE}")
    con_asesor(caido)
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert r["modo"] == "determinista" and CLAVE not in r["texto"]
    detalles = [e["detalle"] for e in db.todos("select detalle from eventos where paso='asesor sin respuesta'")]
    assert detalles and not any(CLAVE in d or "agentes.prueba" in d for d in detalles)


def test_si_se_agota_el_plazo_no_espera_al_modelo_y_corta_la_sesion(con_asesor, monkeypatch):
    s = con_asesor(Servicio([corriendo(), mensaje("Pensando…")]))   # nunca termina
    reloj = itertools.count(0, 10)
    monkeypatch.setattr(asesor, "_reloj", lambda: next(reloj))
    monkeypatch.setattr(llm, "activo", lambda: True)

    def no_debe_llamarse(*a, **k):
        raise AssertionError("tras agotar el plazo no se espera al modelo de lenguaje")
    monkeypatch.setattr(asistente, "_con_modelo", no_debe_llamarse)
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert r["modo"] == "determinista" and "agotó el tiempo" in r["texto"]
    assert "user.interrupt" in s.tipos_enviados()


def test_una_accion_que_no_aparece_en_los_eventos_cae_a_otra_via(con_asesor):
    fantasma = {"id": f"sevt_{next(_ids)}", "type": "session.status_idle",
                "stop_reason": {"type": "requires_action", "event_ids": ["sevt_que_no_existe"]}}
    con_asesor(Servicio([corriendo(), fantasma]))
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert r["modo"] == "determinista" and "no atiende" in r["texto"]


def test_la_pantalla_sigue_respondiendo_si_el_servicio_falla(con_asesor, cliente):
    con_asesor(Servicio(crear=500))
    r = cliente.post("/admin/asistente", data={"pregunta": "¿Cuántos gastos hay en revisión?"})
    assert r.status_code == 200 and "Sin modelo: consultas directas" in r.text


def test_la_pantalla_marca_las_respuestas_del_asesor(con_asesor, cliente):
    con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    r = cliente.post("/admin/asistente", data={"pregunta": "¿Hay gastos en revisión?"})
    assert r.status_code == 200 and "Asesor con herramientas" in r.text


# ---------- herramientas propias ----------
def test_cotizacion_por_numero_o_por_codigo_de_viaje(nuevo_viaje):
    v = nuevo_viaje()
    sid = v["solicitud_id"]
    for forma in (f"#{sid}", str(sid), f"Cotización #{sid}", v["codigo"]):
        r = asistente.Rastro()
        salida = asesor.despachar(r, "opciones_de_cotizacion", {"cotizacion": forma}, _admin())
        assert salida["cotizacion"] == f"#{sid}" and salida["viaje"] == v["codigo"] and salida["vuelos"]
        assert ("cotizacion", sid) in r.fuentes and ("viaje", v["id"]) in r.fuentes
    opcion = salida["vuelos"][0]["opcion_id"]
    desglose = asesor.despachar(asistente.Rastro(), "desglose_de_opcion", {"cotizacion": f"#{sid}", "opcion_id": opcion}, _admin())
    assert desglose["lineas"] and desglose["total"] == salida["vuelos"][0]["costo_total_esperado"]
    assert "ganador_segun_probabilidad_de_cambio" in asesor.despachar(asistente.Rastro(), "sensibilidad", {"cotizacion": sid}, _admin())
    assert "error" in asesor.despachar(asistente.Rastro(), "opciones_de_cotizacion", {"cotizacion": "#9999999"}, _admin())
    assert "error" in asesor.despachar(asistente.Rastro(), "opciones_de_cotizacion", {"cotizacion": "la de ayer"}, _admin())
    assert "reglas" in asesor.despachar(asistente.Rastro(), "reglas_de_aerolinea", {"aerolinea": "Avianca"}, _admin())


def test_justificaciones_de_gasto_trae_la_transcripcion_de_la_nota_de_voz(piloto_con_gastos):
    gid = piloto_con_gastos["gastos"][1]
    db.insertar("justificaciones", gasto_id=gid, usuario_id=piloto_con_gastos["id"], canal="telegram", tipo="audio",
                texto="Parqueadero cerca de la casa que grabamos.", transcripcion="hecha", palabras=7, creado=db.ahora())
    r = asistente.Rastro()
    salida = asesor.despachar(r, "justificaciones_de_gasto", {"id": gid}, _admin())
    nota = salida["justificaciones"][-1]
    assert nota == {"tipo": "nota de voz", "canal": "telegram", "persona": piloto_con_gastos["codigo"], "creado": nota["creado"],
                    "texto": "Parqueadero cerca de la casa que grabamos.", "transcripcion": "hecha"}
    assert ("gasto", gid) in r.fuentes and r.pasos == ["justificaciones_de_gasto"]
    assert "error" in asesor.despachar(asistente.Rastro(), "justificaciones_de_gasto", {"id": "abc"}, _admin())


def test_viajes_de_dice_de_que_cotizacion_nacio(piloto_con_gastos):
    salida = asistente.ejecutar(asistente.Rastro(), "viajes_de", {"persona": piloto_con_gastos["codigo"]})
    v = piloto_con_gastos["viaje"]
    assert any(x["viaje"] == v["codigo"] and x["cotizacion"] == f"#{v['solicitud_id']}" for x in salida["viajes"])


def test_kpi_trae_meta_y_semaforo_como_el_tablero():
    from app.servicios import kpis
    salida = asesor.despachar(asistente.Rastro(), "kpi", {"nombre": "pendientes_revision"}, _admin())
    tablero = kpis.evaluar({}, ["pendientes_revision"])[0]
    assert (salida["valor"], salida["meta"], salida["semaforo"]) == (tablero["valor"], tablero["meta"], tablero["estado"])
    otro = next(n for n in metricas.CATALOGO if n not in kpis.KPIS)
    sin_meta = asesor.despachar(asistente.Rastro(), "kpi", {"nombre": otro}, _admin())
    assert "valor" in sin_meta and "semaforo" not in sin_meta


def test_recortar_deja_json_valido_dentro_del_tope():
    datos = {"gastos": [{"gasto": f"#{i}", "comercio": "x" * 200} for i in range(400)], "totales_por_estado": [{"estado": "aprobado", "total_usd": 1.5}]}
    texto = asesor.recortar(datos, maximo=5_000)
    salida = json.loads(texto)
    assert len(texto) <= 5_000 and salida["totales_por_estado"] == datos["totales_por_estado"] and "recortado" in salida
    assert json.loads(asesor.recortar({"texto": "y" * 10_000}, maximo=1_000))["error"]


def test_el_registro_de_eventos_no_cambia_sin_asesor():
    antes = len(db.todos("select id from eventos where paso='asesor sin respuesta'"))
    asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert len(db.todos("select id from eventos where paso='asesor sin respuesta'")) == antes


# ---------- guion de mantenimiento ----------
def test_el_guion_imprime_las_herramientas_en_json(capsys):
    from datos import asesor as guion
    assert guion.main(["--esquemas"]) == 0
    assert json.loads(capsys.readouterr().out) == asesor.ESQUEMAS
    assert guion.main(["--sistema"]) == 0 and asesor.SISTEMA in capsys.readouterr().out
    assert guion.main(["--verificar"]) == 1   # sin configuración no llama a ningún servicio
    assert "Falta configurar" in capsys.readouterr().out


def test_verificar_detecta_lo_que_separa_al_agente_del_codigo():
    from datos import asesor as guion
    igual = {"system": asesor.SISTEMA, "tools": [dict(e) for e in asesor.ESQUEMAS]}
    assert guion.diferencias(igual) == []
    distinto = {"system": asesor.SISTEMA + "\nSi falta un dato, pídelos todos antes de consultar.",
                "tools": [{"type": "agent_toolset_20260401"}, *asesor.ESQUEMAS[1:], {"type": "custom", "name": "borrar_gasto"}]}
    problemas = " ".join(guion.diferencias(distinto))
    assert "mensaje de sistema" in problemas and "persona" in problemas and "borrar_gasto" in problemas and "del servicio" in problemas


def test_sincronizar_sube_el_sistema_y_las_herramientas(con_asesor, capsys):
    from datos import asesor as guion
    recibido = {}

    def servicio(request):
        if request.method == "GET":
            return httpx.Response(200, json={"id": "agent_prueba", "version": 3, "system": "otro", "tools": [{"type": "agent_toolset_20260401"}]})
        recibido.update(json.loads(request.content))
        return httpx.Response(200, json={**recibido, "id": "agent_prueba", "version": 4})
    con_asesor(servicio)
    assert guion.main(["--sincronizar"]) == 0
    assert recibido["version"] == 3 and recibido["system"] == asesor.SISTEMA and recibido["tools"] == asesor.ESQUEMAS
    assert "versión 3 → 4" in capsys.readouterr().out


def test_el_mensaje_de_sistema_nombra_todos_los_motivos_y_permisos():
    from app.servicios import acceso, validacion
    assert [m for m in validacion.MOTIVOS if m not in asesor.SISTEMA] == []
    assert all(rol in asesor.SISTEMA for rol in acceso.NOMBRE_ROL if rol != "admin")


def test_kpi_todos_devuelve_el_tablero_en_una_consulta():
    from app.servicios import kpis
    salida = asesor.despachar(asistente.Rastro(), "kpi", {"nombre": "todos"}, _admin())
    assert [k["nombre"] for k in salida["indicadores"]] == list(kpis.KPIS)
    assert sum(salida["resumen"].values()) == len(kpis.KPIS)
    assert all({"meta", "semaforo", "valor"} <= set(k) for k in salida["indicadores"])
