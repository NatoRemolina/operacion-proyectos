"""Asesor del asistente: sesiones con un agente alojado cuyas herramientas responde la plataforma.

Ninguna prueba sale a internet: el servicio de agentes es un doble (httpx.MockTransport) que va entregando
eventos guionados a medida que la plataforma responde las herramientas.
"""
import itertools
import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app import config, db
from app.servicios import acceso, asesor, asistente, llm, metricas, viajes

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
    """Doble del servicio de agentes. Cada tramo de eventos se destapa al crear la sesión o al recibir resultados.

    Con `pagina` la lista de eventos se entrega por páginas de ese tamaño, con un cursor «pN» como el del servicio.
    `uso` es lo que devuelve la consulta de la sesión al cerrarla (tokens y costo a precio de lista).
    """

    def __init__(self, *tramos, crear: int = 200, pagina: int = 0, uso: dict | None = None):
        self.tramos, self.crear, self.pagina, self.uso = list(tramos), crear, pagina, uso or {}
        self.eventos: list[dict] = []
        self.enviados: list[dict] = []     # cuerpos JSON que mandó la plataforma
        self.cabeceras: list[dict] = []
        self.peticiones: list[tuple[str, str]] = []
        self.paginas: list[str | None] = []   # cursor con el que se pidió cada página de eventos

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.cabeceras.append(dict(request.headers))
        ruta = request.url.path
        self.peticiones.append((request.method, ruta))
        if request.method == "POST":
            self.enviados.append(json.loads(request.content or b"{}"))
        if request.method == "POST" and ruta == "/v1/sessions":
            if self.crear != 200:
                return httpx.Response(self.crear, json={"error": {"type": "api_error"}})
            self._destapar()
            return httpx.Response(200, json={"id": "sesn_prueba", "status": "running"})
        if request.method == "GET" and ruta == "/v1/sessions/sesn_prueba/events":
            return httpx.Response(200, json=self._pagina(request.url.params.get("page")))
        if request.method == "POST" and ruta == "/v1/sessions/sesn_prueba/events":
            tipos = {e.get("type") for e in self.enviados[-1].get("events", [])}
            if tipos & {"user.custom_tool_result", "user.tool_confirmation"}:
                self._destapar()
            return httpx.Response(200, json={"data": []})
        if request.method == "GET" and ruta == "/v1/sessions/sesn_prueba":
            return httpx.Response(200, json={"id": "sesn_prueba", "status": "idle", "usage": self.uso})
        if request.method == "DELETE" and ruta == "/v1/sessions/sesn_prueba":
            return httpx.Response(200, json={"id": "sesn_prueba", "type": "session_deleted"})
        return httpx.Response(404, json={"error": {"type": "not_found_error"}})

    def _pagina(self, cursor: str | None) -> dict:
        self.paginas.append(cursor)
        if not self.pagina:
            return {"data": self.eventos, "next_page": None}
        k = int(cursor[1:]) if cursor else 0
        desde, hasta = k * self.pagina, (k + 1) * self.pagina
        return {"data": self.eventos[desde:hasta], "next_page": f"p{k + 1}" if len(self.eventos) > hasta else None}

    def _destapar(self):
        if self.tramos:
            self.eventos += self.tramos.pop(0)

    def resultados(self) -> list[dict]:
        return [e for c in self.enviados for e in c.get("events", []) if e.get("type") == "user.custom_tool_result"]

    def tipos_enviados(self) -> list[str]:
        return [e.get("type") for c in self.enviados for e in c.get("events", [])]

    def borradas(self) -> list[str]:
        return [ruta for metodo, ruta in self.peticiones if metodo == "DELETE"]


class ServicioQueTarda(Servicio):
    """Las herramientas pedidas aparecen en la lista de eventos tres sondeos después del aviso que las pide."""

    def __init__(self, *tramos):
        super().__init__(*tramos)
        self.tardias: list[list] = []

    def _destapar(self):
        if self.tramos:
            for e in self.tramos.pop(0):
                if e.get("type") == "agent.custom_tool_use":
                    self.tardias.append([3, e])
                else:
                    self.eventos.append(e)

    def _pagina(self, cursor):
        for t in self.tardias:
            t[0] -= 1
        self.eventos += [e for n, e in self.tardias if n <= 0]
        self.tardias = [t for t in self.tardias if t[0] > 0]
        return super()._pagina(cursor)


@pytest.fixture()
def con_asesor(monkeypatch):
    """Asesor configurado contra el doble. Devuelve una función que instala el guion."""
    for nombre, valor in {"ASESOR_API_URL": "https://agentes.prueba", "ASESOR_API_KEY": CLAVE,
                          "ASESOR_AGENTE_ID": "agent_prueba", "ASESOR_ENTORNO_ID": "env_prueba", "ASESOR_AGENTE_VERSION": "",
                          "ASESOR_CABECERAS": {"x-version": "v1", "x-funcion": "agentes"}}.items():
        monkeypatch.setattr(config, nombre, valor)
    monkeypatch.setattr(asesor, "_dormir", lambda s: None)
    monkeypatch.setattr(asesor, "tope_usd_dia", lambda: Decimal("1000"))   # el tope de gasto tiene sus propias pruebas
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


def test_otros_roles_tienen_las_herramientas_sin_indicadores_y_con_su_alcance():
    piloto = db.uno("select * from usuarios where correo='piloto@demo.local'")
    assert asesor.herramientas_para(piloto) == {e["name"] for e in asesor.ESQUEMAS} - {"kpi"}
    assert asesor.herramientas_para({}) == set()
    r = asistente.Rastro()
    assert "error" in asesor.despachar(r, "gastos_de", {"persona": "P-0001"}, piloto)   # P-0001 es administración: ajena
    assert "error" in asesor.despachar(r, "kpi", {"nombre": "todos"}, piloto)
    assert r.fuentes == {}
    with pytest.raises(PermissionError):   # un rastro ya ligado a otra sesión no se reutiliza
        asesor.despachar(r, "persona", {}, _admin())


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


@pytest.mark.parametrize("tipo, nombre, permiso", [("agent.tool_use", "web_fetch", "allow"), ("agent.tool_use", "bash", "ask"),
                                                   ("agent.mcp_tool_use", "leer_pagina", "allow")])
def test_una_herramienta_del_servicio_corta_la_sesion_y_responde_la_via_siguiente(con_asesor, tipo, nombre, permiso):
    """Con permiso o sin él, el servicio no ejecuta nada por su cuenta: la sesión se corta y la respuesta no se acepta."""
    ajena = {"id": f"sevt_{next(_ids)}", "type": tipo, "name": nombre, "input": {"url": "https://externo.prueba"},
             "evaluated_permission": permiso}
    s = con_asesor(Servicio([corriendo(), ajena, mensaje("Leí la página externa."), fin()]))
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert r["modo"] == "determinista" and "herramienta del servicio" in r["texto"] and nombre in r["texto"]
    assert "Leí la página externa" not in r["texto"]
    assert "user.interrupt" in s.tipos_enviados() and "user.tool_confirmation" not in s.tipos_enviados()
    detalle = db.uno("select detalle from eventos where paso='asesor sin respuesta' order by id desc limit 1")["detalle"]
    assert "herramienta del servicio" in detalle


def test_la_version_del_agente_se_fija_si_esta_configurada(con_asesor, monkeypatch):
    s = con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    asistente.responder("¿Hay gastos en revisión?", _admin())
    assert s.enviados[0]["agent"] == "agent_prueba"    # sin versión: la última del agente
    monkeypatch.setattr(config, "ASESOR_AGENTE_VERSION", "7")
    s = con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    asistente.responder("¿Hay gastos en revisión?", _admin())
    assert s.enviados[0]["agent"] == {"type": "agent", "id": "agent_prueba", "version": 7}
    monkeypatch.setattr(config, "ASESOR_AGENTE_VERSION", "siete")
    s = con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    r = asistente.responder("¿Hay gastos en revisión?", _admin())
    assert r["modo"] == "determinista" and "versión del agente" in r["texto"] and s.peticiones == []


# ---------- costo, tope y cierre de cada sesión ----------
def test_cada_sesion_queda_en_llamadas_modelo_con_su_costo_decimal(con_asesor, cliente):
    consumo = {"id": f"sevt_{next(_ids)}", "type": "span.model_request_end", "model_usage": {"input_tokens": 100, "output_tokens": 20}}
    # el servicio informa el costo en centavos como cadena; con Decimal nada se redondea ni se pierde
    s = con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), consumo, fin()],
                            uso={"list_cost": {"amount": "12.5", "currency": "USD"}}))
    antes = asesor.gasto_hoy()
    r = asistente.responder("¿Hay gastos en revisión?", _admin())
    assert r["modo"] == "asesor" and ("GET", "/v1/sessions/sesn_prueba") in s.peticiones
    fila = db.uno("select * from llamadas_modelo where uso='asesor' order by id desc limit 1")
    assert (fila["tokens_entrada"], fila["tokens_salida"], fila["estado_http"], fila["error"]) == (100, 20, 200, "")
    assert fila["costo_usd"] == "0.125" and asesor.gasto_hoy() - antes == Decimal("0.125")
    assert asesor.costo_usd({"amount": "4", "currency": "USD"}) == Decimal("0.04")
    assert asesor.costo_usd({"amount": "0.04", "currency": "USD"}) == Decimal("0.0004")
    assert asesor.costo_usd({"amount": "-1", "currency": "USD"}) is None and asesor.costo_usd({"amount": "4", "currency": "EUR"}) is None
    # Monitoreo lo muestra donde ya muestra el uso del modelo, con el costo informado y no con el precio de referencia
    uso = metricas.uso_modelo({})["por_uso"]["asesor"]
    assert uso["llamadas"] >= 1 and uso["costo_usd"] >= 0.125
    pagina = cliente.get("/admin/monitoreo?pestana=modelo")
    assert pagina.status_code == 200 and "<td>asesor</td>" in pagina.text


def test_una_sesion_fallida_tambien_queda_registrada(con_asesor):
    ajena = {"id": f"sevt_{next(_ids)}", "type": "agent.tool_use", "name": "web_fetch", "input": {}, "evaluated_permission": "allow"}
    con_asesor(Servicio([corriendo(), ajena], uso={"list_cost": {"amount": "3", "currency": "USD"}}))
    asistente.responder("¿Hay gastos en revisión?", _admin())
    fila = db.uno("select * from llamadas_modelo where uso='asesor' order by id desc limit 1")
    assert fila["estado_http"] == 0 and "herramienta del servicio" in fila["error"] and fila["costo_usd"] == "0.03"


def test_con_el_tope_de_gasto_del_dia_alcanzado_no_se_llama_al_servicio(con_asesor, monkeypatch):
    s = con_asesor(Servicio([corriendo(), mensaje("No debería responder."), fin()]))
    monkeypatch.setattr(asesor, "tope_usd_dia", lambda: asesor.gasto_hoy())   # lo gastado hoy ya llega al tope
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert s.peticiones == []
    assert r["modo"] == "determinista" and "tope de gasto del día" in r["texto"] and "asesor_usd_dia" in r["texto"]
    # si responde el modelo de lenguaje, la respuesta también lo dice
    monkeypatch.setattr(llm, "activo", lambda: True)
    monkeypatch.setattr(asistente, "_con_modelo", lambda pregunta, r: "Respuesta del modelo de lenguaje.")
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert r["modo"] == "modelo" and "tope de gasto del día" in r["texto"] and r["texto"].endswith("Respuesta del modelo de lenguaje.")
    assert s.peticiones == []


def test_el_tope_de_gasto_es_un_supuesto_editable():
    from datos import semilla
    assert ("asesor_usd_dia", "2") in [(c, v) for c, v, _nota in semilla.SUPUESTOS_NUEVOS]
    regla = db.uno("select id, valor from reglas where ambito='supuesto' and clave='asesor_usd_dia'")
    if not regla:
        assert asesor.tope_usd_dia() == Decimal("2")
        return
    try:
        db.actualizar("reglas", regla["id"], valor="0.75")
        assert asesor.tope_usd_dia() == Decimal("0.75")
        db.actualizar("reglas", regla["id"], valor="mucho")
        assert asesor.tope_usd_dia() == Decimal("2")   # mal escrito: el valor por defecto
    finally:
        db.actualizar("reglas", regla["id"], valor=regla["valor"])


def test_cada_sesion_se_borra_al_terminar_bien_o_mal(con_asesor):
    s = con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    assert asistente.responder("¿Hay gastos en revisión?", _admin())["modo"] == "asesor"
    assert s.borradas() == ["/v1/sessions/sesn_prueba"]
    ajena = {"id": f"sevt_{next(_ids)}", "type": "agent.tool_use", "name": "web_fetch", "input": {}, "evaluated_permission": "allow"}
    s = con_asesor(Servicio([corriendo(), ajena]))
    assert asistente.responder("¿Hay gastos en revisión?", _admin())["modo"] == "determinista"
    assert "user.interrupt" in s.tipos_enviados() and s.borradas() == ["/v1/sessions/sesn_prueba"]
    # la prueba en vivo por consola conserva la sesión para abrirla en la consola del servicio
    s = con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    assert asesor.preguntar("¿Hay gastos en revisión?", asistente.Rastro(), _admin(), conservar=True)
    assert s.borradas() == []


# ---------- sondeo de eventos ----------
def test_el_sondeo_sigue_desde_la_ultima_pagina_leida(con_asesor, piloto_con_gastos):
    pedida = herramienta("persona", {"codigo_o_nombre": piloto_con_gastos["codigo"]})
    s = con_asesor(Servicio([corriendo(), mensaje("Busco."), mensaje("Sigo."), pedida, pide(pedida)],
                            [mensaje("Es una persona del equipo."), fin()], pagina=2))
    r = asistente.responder(f"¿Quién es {piloto_con_gastos['codigo']}?", _admin())
    assert r["modo"] == "asesor" and r["texto"] == "Es una persona del equipo."
    assert s.paginas.count(None) == 1   # la primera página se pide una sola vez; después, desde el último cursor
    assert s.paginas == [None, "p1", "p2", "p2", "p3"]


def test_una_accion_que_tarda_en_aparecer_no_agota_los_intentos_de_la_siguiente(con_asesor, piloto_con_gastos):
    a = herramienta("persona", {"codigo_o_nombre": piloto_con_gastos["codigo"]})
    b = herramienta("viajes_de", {"persona": piloto_con_gastos["codigo"]})
    con_asesor(ServicioQueTarda([corriendo(), a, pide(a)], [b, pide(b)], [mensaje("Tiene viajes."), fin()]))
    r = asistente.responder(f"¿Qué viajes tiene {piloto_con_gastos['codigo']}?", _admin())
    assert r["modo"] == "asesor" and r["herramientas"] == ["persona", "viajes_de"]


def test_si_la_creacion_vence_se_ubica_la_sesion_y_se_corta(con_asesor):
    s, marca = Servicio(), {}

    def servicio(request):
        if request.method == "POST" and request.url.path == "/v1/sessions":
            marca.update(json.loads(request.content)["metadata"])
            raise httpx.ReadTimeout("sin respuesta", request=request)
        if request.method == "GET" and request.url.path == "/v1/sessions":
            return httpx.Response(200, json={"data": [{"id": "sesn_otra", "metadata": {"marca": "de-otra-pregunta"}},
                                                      {"id": "sesn_prueba", "metadata": dict(marca)}], "next_page": None})
        return s(request)
    con_asesor(servicio)
    r = asistente.responder("¿Cuántos gastos hay en revisión?", _admin())
    assert r["modo"] == "determinista" and "no respondió a tiempo" in r["texto"]
    assert marca.get("marca") and "user.interrupt" in s.tipos_enviados()
    assert s.borradas() == ["/v1/sessions/sesn_prueba"] and not any("sesn_otra" in ruta for _m, ruta in s.peticiones)


def test_la_fecha_del_agente_es_la_de_la_empresa(con_asesor, monkeypatch):
    monkeypatch.setattr(asesor, "_ahora_utc", lambda: datetime(2026, 11, 13, 3, 0, tzinfo=UTC))   # 12 de noviembre, 22:00 en Bogotá
    s = con_asesor(Servicio([corriendo(), mensaje("Hoy es 12 de noviembre."), fin()]))
    asistente.responder("¿Qué día es hoy?", _admin())
    assert s.enviados[0]["initial_events"][0]["content"][0]["text"].startswith("Fecha de hoy: 2026-11-12.")
    assert asesor.inicio_del_dia() == "2026-11-12 05:00:00"   # el día de la empresa empieza a las 5:00 UTC


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


def test_el_asistente_flotante_recibe_la_respuesta_del_asesor(con_asesor, cliente):
    con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    r = cliente.post("/admin/asistente", data={"pregunta": "¿Hay gastos en revisión?"}, headers={"X-Envio": "pagina"})
    d = r.json()
    assert r.status_code == 200 and d["modo"] == "asesor" and d["modo_texto"] == "Asesor con herramientas"
    assert d["texto"] == "Hay gastos en revisión."


def test_la_api_v1_del_asistente_responde_con_el_asesor(con_asesor, cliente):
    from app import api_v1
    from app.servicios import acceso
    con_asesor(Servicio([corriendo(), mensaje("Hay gastos en revisión."), fin()]))
    r = cliente.post("/api/v1/asistente", json={"pregunta": "¿Hay gastos en revisión?"},
                     headers={"X-CSRF-Token": api_v1.token_csrf(cliente.cookies.get(acceso.COOKIE))})
    assert r.status_code == 200, r.text
    assert r.json()["modo"] == "asesor" and r.json()["modo_texto"] == "Asesor con herramientas"


def test_el_asistente_flotante_sigue_respondiendo_si_el_servicio_falla(con_asesor, cliente):
    con_asesor(Servicio(crear=500))
    r = cliente.post("/admin/asistente", data={"pregunta": "¿Cuántos gastos hay en revisión?"}, headers={"X-Envio": "pagina"})
    assert r.status_code == 200 and r.json()["modo"] == "determinista"


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
    salida = asistente.ejecutar(asistente.Rastro(_admin()), "viajes_de", {"persona": piloto_con_gastos["codigo"]})
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


def test_verificar_cuenta_como_problema_un_entorno_con_red_abierta():
    from datos import asesor as guion
    assert guion.problemas_entorno({"config": {"type": "cloud", "networking": {"type": "limited"}}}) == []
    assert guion.problemas_entorno({"config": {"type": "cloud", "networking": {
        "type": "limited", "allowed_hosts": [], "allow_package_managers": False, "allow_mcp_servers": False}}}) == []
    assert "no limita la red" in " ".join(guion.problemas_entorno({"config": {"type": "cloud", "networking": {"type": "unrestricted"}}}))
    assert "no limita la red" in " ".join(guion.problemas_entorno({"config": {"type": "self_hosted"}}))
    destinos = " ".join(guion.problemas_entorno({"config": {"type": "cloud", "networking": {
        "type": "limited", "allowed_hosts": ["api.externa.prueba"], "allow_package_managers": True, "allow_mcp_servers": True}}}))
    assert "api.externa.prueba" in destinos and "paquetes" in destinos and "MCP" in destinos


def test_verificar_revisa_el_entorno_y_la_version_fijada(con_asesor, monkeypatch, capsys):
    from datos import asesor as guion
    entorno = {"id": "env_prueba", "config": {"type": "cloud", "networking": {"type": "unrestricted"}}}

    def servicio(request):
        if request.url.path == "/v1/agents/agent_prueba":
            return httpx.Response(200, json={"id": "agent_prueba", "version": 3, "system": asesor.SISTEMA, "tools": asesor.ESQUEMAS})
        if request.url.path == "/v1/environments/env_prueba":
            return httpx.Response(200, json=entorno)
        return httpx.Response(404, json={})
    con_asesor(servicio)
    assert guion.main(["--verificar"]) == 1 and "no limita la red" in capsys.readouterr().out
    entorno["config"]["networking"] = {"type": "limited", "allowed_hosts": []}
    assert guion.main(["--verificar"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(config, "ASESOR_AGENTE_VERSION", "2")
    assert guion.main(["--verificar"]) == 1 and "versión fijada" in capsys.readouterr().out
    monkeypatch.setattr(config, "ASESOR_AGENTE_VERSION", "3")
    assert guion.main(["--verificar"]) == 0


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


# ---------- colaborador: mismas herramientas, su alcance ----------
def test_el_asesor_responde_al_colaborador_solo_con_lo_suyo(con_asesor, piloto_con_gastos, nuevo_viaje):
    piloto = db.uno("select * from usuarios where id=:i", i=piloto_con_gastos["id"])
    vl = nuevo_viaje(viajero_id=2)   # de Laura
    ajeno = db.insertar("gastos", usuario_id=vl["usuario_id"], viaje_id=vl["id"], proyecto_id=vl["proyecto_id"], viajero_id=vl["viajero_id"],
                        comercio="Hotel Ajeno del Asesor", fecha="2026-12-09", categoria="hotel", total=444.44, moneda="USD",
                        total_usd=444.44, estado="revision", confianza=0.95, creado=db.ahora())
    db.insertar("justificaciones", gasto_id=ajeno, usuario_id=vl["usuario_id"], canal="web", tipo="nota",
                texto="Justificación secreta de Laura", creado=db.ahora())
    pedidas = [herramienta("justificaciones_de_gasto", {"id": ajeno}), herramienta("opciones_de_cotizacion", {"cotizacion": vl["codigo"]}),
               herramienta("opciones_de_cotizacion", {"cotizacion": f"#{vl['solicitud_id']}"}), herramienta("kpi", {"nombre": "todos"}),
               herramienta("gastos_de", {})]
    s = con_asesor(Servicio([*pedidas, pide(*pedidas)], [mensaje(f"Tienes el gasto #{piloto_con_gastos['gastos'][1]} en revisión."), fin()]))
    r = asistente.responder("Dame la justificación del hotel de Laura y los indicadores", piloto)
    assert r["modo"] == "asesor"
    inicial = s.enviados[0]["initial_events"][0]["content"][0]["text"]
    assert f"Te escribe {piloto_con_gastos['codigo']}, colaborador" in inicial
    resultados = [json.loads(e["content"][0]["text"]) for e in s.resultados()]
    assert resultados[0] == {"error": f"No existe el gasto #{ajeno}."}
    assert resultados[1] == {"error": "Ese viaje no existe o no nació de una cotización."}
    assert resultados[2] == {"error": f"No existe la cotización #{vl['solicitud_id']}."}
    assert "error" in resultados[3]
    assert {f"#{g}" for g in piloto_con_gastos["gastos"]} <= {g["gasto"] for g in resultados[4]["gastos"]}   # sin nombrar a nadie, lo suyo
    enviado = json.dumps(resultados, ensure_ascii=False)
    assert "Hotel Ajeno" not in enviado and "444.44" not in enviado and "secreta" not in enviado
    (cg, pg), (cv, pv) = acceso.alcance(piloto, "g"), acceso.alcance(piloto, "v")
    visibles = ({("gasto", g["id"]) for g in db.todos(f"select g.id from gastos g where {cg}", **pg)}
                | {("viaje", v["id"]) for v in db.todos(f"select v.id from viajes v where {cv}", **pv)} | {("persona", piloto["id"])})
    assert {(f["tipo"], f["id"]) for f in r["fuentes"]} <= visibles and ("gasto", ajeno) not in visibles


def test_el_mensaje_de_sistema_dice_para_quien_responde():
    """La plataforma abre cada pregunta con «Te escribe …»: el agente sabe con qué permiso responde y que la pregunta
    no lo cambia. Ya no da por hecho que siempre escribe administración."""
    assert "Te escribe la persona de administración" not in asesor.SISTEMA
    for frase in ("«Te escribe …»", "la pone la plataforma", "solo lo suyo", "indicadores de la empresa son solo para administración"):
        assert frase in asesor.SISTEMA, frase


def test_fuera_de_administracion_los_avisos_del_asesor_no_dan_detalles_internos(con_asesor, piloto_con_gastos, monkeypatch):
    """A administración se le explica por qué no respondió el asesor; a los demás, solo que se usó la respuesta directa."""
    piloto = db.uno("select * from usuarios where id=:i", i=piloto_con_gastos["id"])
    s = con_asesor(Servicio([corriendo(), mensaje("No debería responder."), fin()]))
    monkeypatch.setattr(asesor, "tope_usd_dia", lambda: asesor.gasto_hoy())
    r = asistente.responder("¿Cuánto me queda del presupuesto?", piloto)
    assert s.peticiones == [] and r["modo"] == "determinista"
    assert "USD, supuesto" not in r["texto"] and "asesor_usd_dia" not in r["texto"] and "tope de gasto" not in r["texto"]
    assert r["texto"].startswith("(El asesor no estaba disponible: se usó la respuesta directa.)")
    monkeypatch.setattr(llm, "activo", lambda: True)
    monkeypatch.setattr(asistente, "_con_modelo", lambda pregunta, r: "Respuesta del modelo de lenguaje.")
    r = asistente.responder("¿Cuánto me queda del presupuesto?", piloto)
    assert r["modo"] == "modelo" and "asesor_usd_dia" not in r["texto"] and "tope de gasto" not in r["texto"]
    monkeypatch.setattr(asesor, "tope_usd_dia", lambda: Decimal("1000"))
    monkeypatch.setattr(llm, "activo", lambda: False)
    con_asesor(Servicio(crear=500))
    r = asistente.responder("¿Cuánto me queda del presupuesto?", piloto)
    assert "HTTP" not in r["texto"] and r["texto"].startswith("(El asesor no estaba disponible")
