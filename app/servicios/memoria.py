"""Memoria del asistente: fichas de trazabilidad y el índice donde se buscan por significado.

Una ficha es un texto corto en español sobre un hecho (un gasto, un viaje, una decisión, una nota,
un mensaje o un evento) con metadatos que dicen de quién es y de qué viaje. Las cifras que da el
asistente NO salen de aquí: salen de consultas exactas por ID. El índice sirve para encontrar por
significado en los textos libres (notas, motivos, alertas, mensajes).

Puerto: `guardar(fichas)`, `borrar(ids)`, `buscar(texto, filtros, k)`. Dos adaptadores:
- `Local` (por defecto, sin claves): palabras sobre la tabla `fichas_rag`.
- `Pinecone` (con PINECONE_API_KEY y PINECONE_HOST): API HTTP de documentos con incrustación
  integrada; se le envía texto, no vectores. La tabla local se mantiene igual como respaldo.

Las fichas llevan códigos (P-0002, V-2026-0001), nunca nombres, correos ni contraseñas.
"""
import hashlib
import json
import re
import unicodedata

import httpx
from sqlalchemy import Column, Integer, Text, delete, insert

from .. import config, db
from . import eventos, viajes

fichas_rag = db._tabla(
    "fichas_rag",  # índice local y copia de lo enviado al externo
    Column("ficha_id", Text, unique=True), Column("tipo", Text), Column("entidad", Text), Column("entidad_id", Integer),
    Column("persona_id", Integer), Column("persona", Text), Column("viaje_id", Integer), Column("viaje", Text),
    Column("proyecto_id", Integer), Column("fecha", Text), Column("canal", Text),
    Column("texto", Text), Column("normalizado", Text), Column("actualizado", Text),
)
indice_rag = db._tabla(
    "indice_rag",  # qué versión de cada ficha tiene cada destino: solo se envía lo que cambió
    Column("destino", Text), Column("entidad", Text), Column("entidad_id", Integer), Column("ficha_id", Text),
    Column("huella", Text), Column("indexado_en", Text),
)

METADATOS = ("tipo", "entidad", "entidad_id", "persona_id", "persona", "viaje_id", "viaje", "proyecto_id", "fecha", "canal")
FILTRABLES = ("persona_id", "viaje_id", "proyecto_id", "tipo", "entidad")
ESTADO_GASTO = {"aprobado_auto": "aprobado automático", "aprobado": "aprobado", "revision": "en revisión",
                "rechazado": "rechazado", "procesando": "procesando"}
# Pasos de la bitácora que cuentan algo de la persona o del viaje; los demás (lecturas, consultas) son ruido
EVENTOS_RELEVANTES = ("presupuesto aprobado", "presupuesto rechazado", "presupuesto actualizado", "viaje reabierto", "viaje cerrado",
                      "enviado a revisión", "rechazado en revisión", "corregido y aprobado", "corregido, sigue en revisión",
                      "aprobado con excepción", "asignado a viaje")


class ErrorIndice(RuntimeError):
    """Fallo al hablar con el índice externo. El mensaje nunca lleva la clave."""


# ---------- texto ----------
VACIAS = set("""a al algo ante con como contra cual cuales de del desde donde el ella ellas en entre era es esa ese eso esta este esto
fue ha han hay la las le les lo los mas me mi mis muy no nos o para pero por que quien quienes se ser si sin sobre su sus te tu un una
uno unos y ya yo dime cuanto cuanta cuantos cuantas cual muestra muestrame""".split())


def normalizar(texto: str | None) -> str:
    """Minúsculas, sin tildes y solo letras y números: «Parqueadero» y «parqueadero» son la misma palabra."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def palabras(texto: str) -> list[str]:
    """Términos de búsqueda: sin palabras vacías y con el plural recortado («recibos» encuentra «recibo»)."""
    salida = []
    for p in normalizar(texto).split():
        if len(p) < 3 or p in VACIAS:
            continue
        p = p[:-1] if len(p) > 4 and p.endswith("s") else p
        if p not in salida:
            salida.append(p)
    return salida


def _dinero(v, m="USD") -> str:
    return "sin importe" if v is None else f"{v:,.2f} {m or ''}".strip()


# ---------- fichas ----------
def _ficha(tipo: str, entidad: str, entidad_id: int, texto: str, persona_id=None, viaje_id=None, codigos: dict | None = None,
           proyecto_id=None, fecha=None, canal=None) -> dict:
    return {"id": f"{entidad}-{entidad_id}", "tipo": tipo, "entidad": entidad, "entidad_id": entidad_id,
            "persona_id": persona_id, "persona": viajes.codigo_persona(persona_id) if persona_id else None,
            "viaje_id": viaje_id, "viaje": (codigos or {}).get(viaje_id), "proyecto_id": proyecto_id,
            "fecha": (fecha or "")[:19] or None, "canal": canal, "texto": " ".join(texto.split())[:1500]}


def _viajes_base() -> dict[int, dict]:
    filas = db.todos("""select v.id, v.creado, v.usuario_id, v.proyecto_id, v.ida, v.regreso, v.presupuesto_usd, v.estado, v.motivo,
                        s.origen, s.destino, p.nombre proyecto
                        from viajes v left join solicitudes s on s.id=v.solicitud_id left join proyectos p on p.id=v.proyecto_id""")
    for v in filas:
        v["codigo"] = viajes.codigo_viaje(v)
    return {v["id"]: v for v in filas}


def fichas_de_viajes(vs: dict, codigos: dict) -> list[dict]:
    salida = []
    for v in vs.values():
        texto = (f"Viaje {v['codigo']} de {viajes.codigo_persona(v['usuario_id']) if v['usuario_id'] else 'titular sin cuenta'}: "
                 f"{v['origen'] or '?'} → {v['destino'] or '?'}, del {v['ida']} al {v['regreso']}. Proyecto: {v['proyecto'] or 'sin proyecto'}. "
                 f"Presupuesto {_dinero(v['presupuesto_usd'])}. Estado: {viajes.ESTADOS.get(v['estado'], v['estado'])}."
                 + (f" Motivo: {v['motivo']}." if v["motivo"] else ""))
        salida.append(_ficha("viaje", "viajes", v["id"], texto, v["usuario_id"], v["id"], codigos, v["proyecto_id"], v["creado"]))
    return salida


def fichas_de_gastos(vs: dict, codigos: dict) -> list[dict]:
    salida = []
    for g in db.todos("""select g.id, g.comercio, g.fecha, g.categoria, g.total, g.moneda, g.total_usd, g.estado, g.alertas,
                         g.viaje_id, g.proyecto_id, g.usuario_id, g.creado, d.canal
                         from gastos g left join documentos d on d.id=g.documento_id"""):
        # El gasto es de quien viaja; si no tiene viaje, de quien lo cargó
        persona = (vs.get(g["viaje_id"]) or {}).get("usuario_id") or g["usuario_id"]
        alertas = " ".join(db.de_json(g["alertas"], []) or [])
        texto = (f"Gasto #{g['id']} de {viajes.codigo_persona(persona) if persona else 'persona sin cuenta'}"
                 + (f" en el viaje {codigos[g['viaje_id']]}" if g["viaje_id"] in codigos else " sin viaje")
                 + f": {g['comercio'] or 'comercio sin leer'}, {_dinero(g['total'], g['moneda'])}"
                 + (f" ({_dinero(g['total_usd'])})" if g["total_usd"] is not None and g["moneda"] != "USD" else "")
                 + f", categoría {config.CATEGORIAS.get(g['categoria'], g['categoria'] or 'sin categoría')}, fecha del recibo {g['fecha'] or 'sin fecha'}, "
                 f"estado {ESTADO_GASTO.get(g['estado'], g['estado'])}, canal {g['canal'] or 'desconocido'}."
                 + (f" Alertas: {alertas}" if alertas else ""))
        salida.append(_ficha("gasto", "gastos", g["id"], texto, persona, g["viaje_id"], codigos, g["proyecto_id"], g["fecha"] or g["creado"], g["canal"]))
    return salida


def fichas_de_decisiones(vs: dict, codigos: dict) -> list[dict]:
    salida = []
    for d in db.todos("""select d.id, d.motivo, d.razones, d.siguio_recomendacion, d.creado, d.usuario_id, d.proyecto_id, v.id viaje_id
                         from decisiones d left join viajes v on v.solicitud_id=d.solicitud_id"""):
        razones = [config.RAZONES.get(r, r) for r in db.de_json(d["razones"], []) or []]
        if not d["motivo"] and not razones:
            continue
        persona = (vs.get(d["viaje_id"]) or {}).get("usuario_id") or d["usuario_id"]
        siguio = {1: "siguió la recomendación", 0: "no siguió la recomendación"}.get(d["siguio_recomendacion"], "")
        texto = (f"Decisión del viaje {codigos.get(d['viaje_id'], 'sin viaje')} de {viajes.codigo_persona(persona) if persona else '—'}"
                 + (f": {siguio}." if siguio else ".") + (f" Por qué: {d['motivo']}." if d["motivo"] else "")
                 + (f" Razones: {', '.join(razones)}." if razones else ""))
        salida.append(_ficha("decision", "decisiones", d["id"], texto, persona, d["viaje_id"], codigos, d["proyecto_id"], d["creado"]))
    return salida


def fichas_de_evidencias(vs: dict, codigos: dict) -> list[dict]:
    """Notas y audios: su texto, nunca el contenido binario ni la ruta del archivo."""
    salida = []
    for d in db.todos("select id, tipo, texto, canal, creado, usuario_id, viaje_id from documentos where tipo in ('nota','audio') "
                        "and id not in (select documento_id from justificaciones where documento_id is not null)"):
        if d["tipo"] == "nota" and not d["texto"]:
            continue
        cuerpo = d["texto"] or "(sin transcripción)"
        texto = (f"{'Nota escrita' if d['tipo'] == 'nota' else 'Nota de voz'} de {viajes.codigo_persona(d['usuario_id']) if d['usuario_id'] else '—'}"
                 f" en el viaje {codigos.get(d['viaje_id'], 'sin viaje')} (canal {d['canal'] or '—'}): {cuerpo}")
        proyecto = (vs.get(d["viaje_id"]) or {}).get("proyecto_id")
        salida.append(_ficha(d["tipo"], "documentos", d["id"], texto, d["usuario_id"], d["viaje_id"], codigos, proyecto, d["creado"], d["canal"]))
    return salida


def fichas_de_mensajes(vs: dict, codigos: dict) -> list[dict]:
    """Mensajes de Telegram con texto. Nunca los de vínculo (traen un código de un solo uso), comandos ni botones,
    ni las notas que ya quedaron como evidencia."""
    salida = []
    for m in db.todos("""select id, tipo, texto, usuario_id, viaje_id, gasto_id, momento from telegram_mensajes
                         where texto is not null and usuario_id is not null and coalesce(tipo,'') not in ('vinculo','comando','boton','justificacion')
                         and not (tipo='nota' and documento_id is not null)"""):
        if m["texto"].lstrip().startswith("/"):
            continue
        texto = (f"Mensaje de Telegram de {viajes.codigo_persona(m['usuario_id'])} en el viaje {codigos.get(m['viaje_id'], 'sin viaje')}"
                 + (f" (acompaña al gasto #{m['gasto_id']})" if m["gasto_id"] else "") + f": {m['texto']}")
        proyecto = (vs.get(m["viaje_id"]) or {}).get("proyecto_id")
        salida.append(_ficha("mensaje", "telegram_mensajes", m["id"], texto, m["usuario_id"], m["viaje_id"], codigos, proyecto, m["momento"], "telegram"))
    return salida


def fichas_de_justificaciones(vs: dict, codigos: dict) -> list[dict]:
    """Para qué fue cada gasto, con las palabras de la persona (escritas o transcritas de su nota de voz)."""
    salida = []
    for j in db.todos("""select j.id, j.gasto_id, j.tipo, j.texto, j.canal, j.creado, j.usuario_id, g.viaje_id, g.proyecto_id,
                         g.comercio from justificaciones j join gastos g on g.id=j.gasto_id where j.texto is not null"""):
        texto = (f"Justificación del gasto #{j['gasto_id']} ({j['comercio'] or 'comercio sin leer'}) de "
                 f"{viajes.codigo_persona(j['usuario_id']) if j['usuario_id'] else '—'} en el viaje {codigos.get(j['viaje_id'], 'sin viaje')}, "
                 f"{'por nota de voz' if j['tipo'] == 'audio' else 'por escrito'}: {j['texto']}")
        salida.append(_ficha("justificacion", "justificaciones", j["id"], texto, j["usuario_id"], j["viaje_id"], codigos,
                             j["proyecto_id"], j["creado"], j["canal"]))
    return salida


def fichas_de_eventos(vs: dict, codigos: dict) -> list[dict]:
    marcas = ",".join(f"'{p}'" for p in EVENTOS_RELEVANTES)
    gastos_ = {g["id"]: g for g in db.todos("select id, viaje_id, usuario_id, proyecto_id from gastos")}
    salida = []
    for e in db.todos(f"select id, momento, entidad, entidad_id, paso, detalle from eventos where entidad in ('gasto','viaje') and paso in ({marcas})"):
        if e["entidad"] == "viaje":
            v = vs.get(e["entidad_id"]) or {}
            vid, persona, proyecto, sujeto = e["entidad_id"], v.get("usuario_id"), v.get("proyecto_id"), f"viaje {codigos.get(e['entidad_id'], '—')}"
        else:
            g = gastos_.get(e["entidad_id"]) or {}
            vid, proyecto, sujeto = g.get("viaje_id"), g.get("proyecto_id"), f"gasto #{e['entidad_id']}"
            persona = (vs.get(vid) or {}).get("usuario_id") or g.get("usuario_id")
        texto = (f"Evento del {sujeto} de {viajes.codigo_persona(persona) if persona else '—'}: {e['paso']} el {e['momento']}."
                 + (f" Detalle: {e['detalle']}" if e["detalle"] else ""))
        salida.append(_ficha("evento", "eventos", e["id"], texto, persona, vid, codigos, proyecto, e["momento"]))
    return salida


def todas_las_fichas() -> list[dict]:
    vs = _viajes_base()
    codigos = {i: v["codigo"] for i, v in vs.items()}
    salida = []
    for fuente in (fichas_de_viajes, fichas_de_gastos, fichas_de_decisiones, fichas_de_evidencias, fichas_de_justificaciones, fichas_de_mensajes, fichas_de_eventos):
        salida.extend(fuente(vs, codigos))
    return salida


def huella(ficha: dict) -> str:
    return hashlib.sha256(json.dumps(ficha, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _lotes(lista: list, n: int):
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


# ---------- adaptador local ----------
class Local:
    nombre = "local"
    descripcion = "Índice local por palabras (sin servicios externos)"

    def guardar(self, fichas: list[dict]):
        ahora = db.ahora()
        filas = [{"ficha_id": f["id"], **{k: f.get(k) for k in METADATOS}, "texto": f["texto"],
                  "normalizado": normalizar(f["texto"]), "actualizado": ahora} for f in fichas]
        with db.motor.begin() as c:
            for lote in _lotes(filas, 500):
                c.execute(delete(fichas_rag).where(fichas_rag.c.ficha_id.in_([f["ficha_id"] for f in lote])))
                c.execute(insert(fichas_rag), lote)

    def borrar(self, ids: list[str]):
        with db.motor.begin() as c:
            for lote in _lotes(list(ids), 500):
                c.execute(delete(fichas_rag).where(fichas_rag.c.ficha_id.in_(lote)))

    def buscar(self, texto: str, filtros: dict | None = None, k: int = 8) -> list[dict]:
        cond, par = ["1=1"], {}
        for campo, valor in (filtros or {}).items():
            if campo in FILTRABLES and valor not in (None, ""):
                cond.append(f"{campo}=:{campo}"); par[campo] = valor
        terminos = palabras(texto)
        if terminos:
            cond.append("(" + " or ".join(f"normalizado like :t{i}" for i in range(len(terminos))) + ")")
            par.update({f"t{i}": f"%{t}%" for i, t in enumerate(terminos)})
        filas = db.todos(f"select * from fichas_rag where {' and '.join(cond)} order by fecha desc, id desc limit 2000", **par)
        for f in filas:
            # Cuenta cuántos términos distintos aparecen; a igual cuenta, gana el que los repite más
            f["puntaje"] = sum(1 for t in terminos if t in f["normalizado"]) + 0.01 * sum(f["normalizado"].count(t) for t in terminos)
        filas.sort(key=lambda f: -f["puntaje"])
        return [_salida(f, f["ficha_id"]) for f in filas[:k]]


def _salida(f: dict, ficha_id: str) -> dict:
    return {"id": ficha_id, **{k: f.get(k) for k in METADATOS}, "texto": f.get("texto") or "", "puntaje": round(f.get("puntaje") or 0, 3)}


# ---------- adaptador Pinecone ----------
class Pinecone:
    """API de documentos de Pinecone (versión 2026-07), con un campo `texto` que el índice incrusta con su propio modelo."""
    nombre = "pinecone"
    descripcion = "Pinecone: búsqueda por significado con incrustación integrada"
    VERSION = "2026-07"
    CAMPO = "texto"
    LOTE = 96          # tope por petición cuando el índice incrusta el texto
    ESPERA_S = 20

    def __init__(self, host: str, clave: str, espacio: str, transporte: httpx.BaseTransport | None = None):
        self.host, self.clave, self.espacio, self.transporte = host, clave, espacio, transporte

    def _cabeceras(self) -> dict:
        return {"Api-Key": self.clave, "Content-Type": "application/json", "X-Pinecone-Api-Version": self.VERSION}

    def _limpio(self, texto: str) -> str:
        return texto.replace(self.clave, "***") if self.clave else texto

    def _pedir(self, operacion: str, url: str, cuerpo: dict) -> dict:
        try:
            with httpx.Client(transport=self.transporte, timeout=self.ESPERA_S) as c:
                r = c.post(url, json=cuerpo, headers=self._cabeceras())
        except httpx.HTTPError as e:
            # El texto de la excepción puede traer la petición entera: solo se conserva el tipo
            raise ErrorIndice(f"{operacion}: {type(e).__name__}") from None
        if r.status_code >= 400:
            raise ErrorIndice(f"{operacion}: HTTP {r.status_code} {self._limpio(r.text[:160])}".strip())
        try:
            return r.json()
        except ValueError:
            return {}

    def _datos(self, operacion: str, cuerpo: dict) -> dict:
        return self._pedir(operacion, f"https://{self.host}/namespaces/{self.espacio}/documents/{operacion}", cuerpo)

    def guardar(self, fichas: list[dict]):
        documentos = [{"_id": f["id"], self.CAMPO: f["texto"], **{k: f[k] for k in METADATOS if f.get(k) is not None}} for f in fichas]
        for lote in _lotes(documentos, self.LOTE):
            self._datos("upsert", {"documents": lote})

    def borrar(self, ids: list[str]):
        for lote in _lotes(list(ids), 1000):
            self._datos("delete", {"ids": lote})

    @staticmethod
    def filtro(filtros: dict | None) -> dict:
        return {campo: {"$eq": valor} for campo, valor in (filtros or {}).items() if campo in FILTRABLES and valor not in (None, "")}

    def buscar(self, texto: str, filtros: dict | None = None, k: int = 8) -> list[dict]:
        if not texto.strip():   # sin texto no hay nada que incrustar: lo reciente sale del índice local
            return Local().buscar("", filtros, k)
        cuerpo = {"top_k": k, "score_by": [{"type": "embed", "fields": [self.CAMPO], "query": texto[:500]}], "include_fields": ["*"]}
        if self.filtro(filtros):
            cuerpo["filter"] = self.filtro(filtros)
        respuesta = self._datos("search", cuerpo)
        return [_salida({**m, "puntaje": m.get("_score")}, m.get("_id")) for m in respuesta.get("matches") or []]


def crear_indice_pinecone(transporte: httpx.BaseTransport | None = None) -> str:
    """Crea el índice con un campo de texto que Pinecone incrusta (modelo multilingüe, sirve para español). Devuelve su dirección."""
    p = Pinecone("api.pinecone.io", config.PINECONE_API_KEY, "", transporte)
    cuerpo = {"name": config.PINECONE_INDICE, "deployment": {"deployment_type": "managed", "cloud": "aws", "region": "us-east-1"},
              "schema": {"fields": {Pinecone.CAMPO: {"type": "string", "embed": {"model": "multilingual-e5-large"}}}},
              "deletion_protection": "disabled", "tags": {"uso": "asistente"}}
    return p._pedir("crear índice", "https://api.pinecone.io/indexes", cuerpo).get("host", "")


# ---------- selección del adaptador e indexación incremental ----------
def pinecone_activo() -> bool:
    return bool(config.PINECONE_API_KEY and config.PINECONE_HOST)


def externo() -> Pinecone | None:
    # Un espacio por entorno: la base local y la de la nube repiten identificadores y no deben mezclarse
    return Pinecone(config.PINECONE_HOST, config.PINECONE_API_KEY, f"fichas-{config.ENTORNO}") if pinecone_activo() else None


def activo():
    return externo() or Local()


def destinos() -> list:
    """La copia local siempre se mantiene: es el índice sin claves y el respaldo si el externo falla."""
    return [Local()] + ([externo()] if pinecone_activo() else [])


def actualizar(max_envios: int | None = None, todo: bool = False) -> dict:
    """Envía a cada destino solo las fichas nuevas o cambiadas y borra las que ya no existen.

    `max_envios` acota el trabajo (se usa antes de responder); lo que falte se envía en la siguiente vuelta.
    """
    fichas = {f["id"]: f for f in todas_las_fichas()}
    huellas = {i: huella(f) for i, f in fichas.items()}
    resumen = {}
    for destino in destinos():
        previas = {r["ficha_id"]: r["huella"] for r in db.todos("select ficha_id, huella from indice_rag where destino=:d", d=destino.nombre)}
        cambiadas = sorted((f for i, f in fichas.items() if todo or previas.get(i) != huellas[i]), key=lambda f: f["fecha"] or "", reverse=True)
        sobran = [i for i in previas if i not in fichas]
        enviar = cambiadas if max_envios is None else cambiadas[:max_envios]
        try:
            if enviar:
                destino.guardar(enviar)
            if sobran:
                destino.borrar(sobran)
        except ErrorIndice as e:
            resumen[destino.nombre] = {"error": str(e)}
            eventos.registrar("indice", None, "actualización del índice fallida", str(e), destino.nombre)
            continue
        ahora = db.ahora()
        with db.motor.begin() as c:
            for lote in _lotes([f["id"] for f in enviar] + sobran, 500):
                c.execute(delete(indice_rag).where(indice_rag.c.destino == destino.nombre, indice_rag.c.ficha_id.in_(lote)))
            for lote in _lotes(enviar, 500):
                c.execute(insert(indice_rag), [{"destino": destino.nombre, "entidad": f["entidad"], "entidad_id": f["entidad_id"],
                                                "ficha_id": f["id"], "huella": huellas[f["id"]], "indexado_en": ahora} for f in lote])
        resumen[destino.nombre] = {"enviadas": len(enviar), "borradas": len(sobran), "faltan": len(cambiadas) - len(enviar), "total": len(fichas)}
    hechos = sum(r.get("enviadas", 0) + r.get("borradas", 0) for r in resumen.values())
    if hechos:
        eventos.registrar("indice", None, "índice actualizado",
                          " · ".join(f"{d}: {r['enviadas']} enviadas, {r['borradas']} borradas" for d, r in resumen.items() if "error" not in r),
                          ", ".join(resumen))
    return resumen


def buscar(texto: str, filtros: dict | None = None, k: int = 8) -> tuple[list[dict], str]:
    """Devuelve (fichas, adaptador usado). Si el índice externo falla, responde la copia local y lo dice."""
    a = activo()
    try:
        return a.buscar(texto, filtros, k), a.nombre
    except ErrorIndice:
        return Local().buscar(texto, filtros, k), "local (respaldo: falló el índice externo)"


def estado() -> dict:
    a = activo()
    n = db.uno("select count(*) n, max(actualizado) ultima from fichas_rag")
    externa = db.uno("select count(*) n, max(indexado_en) ultima from indice_rag where destino=:d", d=a.nombre)
    return {"adaptador": a.nombre, "descripcion": a.descripcion, "fichas": externa["n"] if a.nombre != "local" else n["n"],
            "actualizado": externa["ultima"], "fichas_locales": n["n"],
            "por_tipo": db.todos("select tipo, count(*) n from fichas_rag group by tipo order by n desc")}
