"""Registro de soportes y gastos, igual para todos los canales (web, celular, correo, Telegram).

Recibe a la persona como parámetro: no depende de que haya una sesión de navegador.
"""
import hashlib
import math
import re
from pathlib import Path

from .. import config, db
from . import almacen, avisos, dinero, envios, eventos, extraccion, llm, revision, validacion


class SoporteRechazado(ValueError):
    """El archivo no se acepta; el mensaje se le muestra a quien lo envió."""


EXTENSIONES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
# Un correo guardado que alguien sube llegó por correo, aunque lo suba desde la web, el celular o la API
FORMATOS_DE_CORREO = ("message/rfc822", "text/html")
TIPOS_ADMITIDOS = "Se aceptan fotos (JPG, PNG, WebP), PDF, correos (.eml) y confirmaciones en HTML (.html)."
CANALES_DE_SUBIDA = ("web", "celular")


def tipo_real(contenido: bytes, nombre: str) -> tuple[str, str] | None:
    """Tipo según el contenido, no según lo que declara quien sube. Devuelve (tipo, extensión) o None."""
    binario = extraccion.tipo_binario(contenido)
    if binario:
        return binario, EXTENSIONES[binario]
    if nombre.lower().endswith((".html", ".htm")) and extraccion.parece_html(contenido):
        return "text/html", "html"
    if nombre.lower().endswith(".eml"):
        cabecera = contenido[:4000].decode("utf-8", "ignore").lower()
        if not cabecera.lstrip().startswith("<") and sum(c in cabecera for c in ("from:", "subject:", "date:", "to:")) >= 2:
            return "message/rfc822", "eml"
    return None


def preparar(contenido: bytes, nombre: str) -> tuple[bytes, str, str]:
    """Lo que se guarda y se lee de un soporte: (contenido, tipo, extensión). Lanza SoporteRechazado si no se admite.

    Una confirmación en HTML se reduce a texto plano, sin scripts, estilos ni enlaces activos, antes de guardarla y de
    enviarla al modelo. La medición de exactitud usa esta misma preparación."""
    tipo = tipo_real(contenido, nombre)
    if not tipo:
        raise SoporteRechazado("Tipo de archivo no admitido. " + TIPOS_ADMITIDOS)
    mime, extension = tipo
    if mime == "text/html":
        texto = extraccion.html_a_texto(contenido)
        if not texto:
            raise SoporteRechazado("La confirmación en HTML no tiene texto legible.")
        return texto.encode(), "text/plain", "txt"
    return contenido, mime, extension


def tipo_audio(contenido: bytes) -> tuple[str, str] | None:
    if contenido[:4] == b"OggS":
        return "audio/ogg", "ogg"
    if contenido[:3] == b"ID3" or contenido[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "audio/mpeg", "mp3"
    if contenido[4:8] == b"ftyp":
        return "audio/mp4", "m4a"
    return None


def nombre_visible(nombre: str) -> str:
    """Nombre original solo para mostrarlo: sin rutas ni caracteres de control."""
    limpio = re.sub(r"[\x00-\x1f\\/]", "_", Path(nombre or "soporte").name)[:120]
    return limpio or "soporte"


def _guardar(contenido: bytes, mime: str, extension: str) -> tuple[str, str]:
    huella = hashlib.sha256(contenido).hexdigest()
    try:
        return almacen.guardar(almacen.clave(huella, extension), contenido, mime), huella
    except Exception as e:
        raise SoporteRechazado(f"No se pudo guardar el archivo ({type(e).__name__}). Intenta de nuevo.") from e


def disposicion(mime: str | None, nombre: str | None) -> str:
    """Cómo se entrega el original: en línea, salvo la confirmación HTML reducida a texto, que solo se descarga."""
    if mime != "text/plain":
        return "inline"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", Path(nombre or "soporte").stem)[:80] or "soporte"
    return f'attachment; filename="{base}.txt"'


def correo_de(texto: str | None) -> dict | None:
    """El remitente y el asunto guardados con el soporte, si llegó como correo; None si no los hay."""
    datos = db.de_json(texto, None) if texto else None
    if not isinstance(datos, dict) or not (datos.get("remitente") or datos.get("asunto")):
        return None
    return {"remitente": datos.get("remitente"), "asunto": datos.get("asunto")}


def _campos_de(gasto: dict) -> dict:
    """Los campos de un gasto ya guardado, con la confianza y las dudas de su lectura original."""
    original = db.de_json(gasto.get("extraido"), {}) or {}
    return {**{c: gasto.get(c) for c in extraccion.CAMPOS if c != "ciudad"},
            "confianza": gasto.get("confianza") or 0, "dudas": original.get("dudas", [])}


def registrar(contenido: bytes, nombre: str, canal: str, usuario: dict | None, viaje: dict | None = None,
              proyecto_id: int | None = None, viajero_id: int | None = None, rapido: bool = False,
              clave_idempotencia: str | None = None, contexto: dict | None = None) -> int:
    """Guarda el soporte, lo lee, lo valida contra la regla del viaje y devuelve el identificador del gasto.

    `clave_idempotencia`: la misma clave y el mismo contenido de la misma persona devuelven el mismo gasto
    (ver `registrar_envio`).
    """
    return registrar_envio(contenido, nombre, canal, usuario, viaje, proyecto_id, viajero_id, rapido,
                           clave_idempotencia, contexto)[0]


def _sin_lectura(error: str) -> dict:
    return {**{c: None for c in extraccion.CAMPOS}, "confianza": 0.0, "dudas": list(extraccion.CAMPOS),
            "origen_dato": "sin datos", "error": error}


def registrar_envio(contenido: bytes, nombre: str, canal: str, usuario: dict | None, viaje: dict | None = None,
                    proyecto_id: int | None = None, viajero_id: int | None = None, rapido: bool = False,
                    clave_idempotencia: str | None = None, contexto: dict | None = None) -> tuple[int, bool]:
    """Como `registrar`, y además dice si el envío era repetido: (gasto, repetido).

    Con clave, el reintento de la misma persona con el mismo archivo y lo mismo pedido (`contexto`; por omisión el viaje,
    el proyecto y el viajero) devuelve el gasto que ya existe, aunque siga en lectura. La misma clave con otro archivo u
    otro viaje lanza `envios.ConflictoEnvio`; si otro proceso la está atendiendo y aún no hay gasto, `envios.EnvioEnCurso`.
    """
    if not contenido:
        raise SoporteRechazado("El archivo está vacío.")
    if len(contenido) > config.MAX_BYTES_SOPORTE:
        raise SoporteRechazado(f"El archivo pesa {len(contenido) / 1e6:.1f} MB; el máximo es {config.MAX_BYTES_SOPORTE / 1e6:.1f} MB.")
    tipo = tipo_real(contenido, nombre)
    if tipo and tipo[0] in FORMATOS_DE_CORREO and canal in CANALES_DE_SUBIDA:
        canal = "correo"
    contenido, mime, extension = preparar(contenido, nombre)
    op = None
    clave = (clave_idempotencia or "").strip()
    if clave and usuario:
        if len(clave) > envios.LARGO_MAXIMO:
            raise SoporteRechazado(f"La clave del envío es demasiado larga (máximo {envios.LARGO_MAXIMO} caracteres).")
        pedido = contexto if contexto is not None else \
            {"viaje_id": viaje["id"] if viaje else None, "proyecto_id": proyecto_id, "viajero_id": viajero_id}
        op, repetido = envios.reclamar(usuario["id"], clave, envios.huella(contenido, pedido))
        if repetido:
            return op["gasto_id"], True
    try:
        return _registrar(contenido, nombre, canal, usuario, viaje, proyecto_id, viajero_id, rapido, mime, extension, op), False
    except Exception:
        if op:
            envios.terminar(op, "fallido")   # libera la concesión: un reintento puede retomarlo o recuperarlo
        raise


def _registrar(contenido: bytes, nombre: str, canal: str, usuario: dict | None, viaje: dict | None, proyecto_id: int | None,
               viajero_id: int | None, rapido: bool, mime: str, extension: str, op: dict | None) -> int:
    nombre = nombre_visible(nombre)
    ruta, huella = _guardar(contenido, mime, extension)
    if viaje:   # el viaje define el proyecto y la persona que viaja
        proyecto_id, viajero_id = viaje["proyecto_id"], viaje["viajero_id"] or viajero_id
    yo = usuario["id"] if usuario else None
    vid = viaje["id"] if viaje else None
    with db.transaccion():
        doc = db.insertar("documentos", nombre=nombre, mime=mime, canal=canal, ruta=ruta, huella=huella, creado=db.ahora(),
                          usuario_id=yo, viaje_id=vid, tipo="soporte",
                          texto=extraccion.remitente_y_asunto(contenido) if mime == "message/rfc822" else None)
        gid = db.insertar("gastos", documento_id=doc, proyecto_id=proyecto_id, viajero_id=viajero_id, viaje_id=vid,
                          estado="procesando", creado=db.ahora(), usuario_id=yo)
        eventos.registrar("gasto", gid, "documento recibido", f"{nombre} ({mime})" + (f" · {viaje['codigo']}" if viaje else ""),
                          f"canal: {canal}")
        if op:
            envios.enlazar(op, gid)   # desde aquí, un reintento con la misma clave recibe este gasto
    try:
        _leer_y_decidir(gid, contenido, mime, nombre, viaje, proyecto_id, rapido, huella, op)
    except envios.EnvioEnCurso:
        raise   # otro proceso recuperó el envío y ya dejó el gasto en revisión
    except Exception:
        envios.marcar_interrumpido(gid)   # nunca queda «procesando» para siempre
        avisos.gasto_registrado(gid)      # el soporte quedó guardado: también se avisa
        raise
    avisos.gasto_registrado(gid)   # apagado sin N8N_WEBHOOK_URL; un fallo del destino no afecta el registro
    return gid


def _leer_y_decidir(gid: int, contenido: bytes, mime: str, nombre: str, viaje: dict | None, proyecto_id: int | None,
                    rapido: bool, huella: str, op: dict | None):
    # Un archivo idéntico ya leído no se vuelve a pagar: se reutiliza su lectura
    previo = db.uno("""select g.extraido from gastos g join documentos d on d.id=g.documento_id
                       where d.huella=:h and g.id<>:i and g.extraido is not null order by g.id limit 1""", h=huella, i=gid)
    marca = llm.RAPIDO.set(rapido)
    try:
        with eventos.cronometro() as t:
            try:
                x = {**db.de_json(previo["extraido"], {}), "origen_dato": "reutilizado", "error": None} if previo else \
                    extraccion.extraer(contenido, mime, nombre, gid)
            except Exception as e:   # un fallo inesperado de la lectura manda el gasto a revisión, como una lectura fallida
                x = _sin_lectura(f"La lectura del recibo falló ({type(e).__name__}). Administración completará los datos.")
    finally:
        llm.RAPIDO.reset(marca)
    eventos.registrar("gasto", gid, "datos extraídos", x.get("error") or f"{x['comercio']} · {x['total']} {x['moneda']} · confianza {x['confianza']:.0%}",
                      f"modelo ({x['origen_dato']})", t())
    # La lectura tarda y va fuera; la decisión, con el viaje bloqueado y releído: lo gastado no cambia mientras se decide
    with db.transaccion() as conexion:
        if op:
            envios.comprobar(op)
        # Primero el viaje y después el gasto: el mismo orden que la revisión y la asignación de viaje, para que dos
        # operaciones a la vez en PostgreSQL no se bloqueen entre sí
        viaje = _vigente(conexion, viaje)
        actual = db.uno("select estado from gastos where id=:i" + ("" if config.ES_SQLITE else " for update"), i=gid)
        if not actual or actual["estado"] != "procesando":
            return   # mientras se leía, alguien lo recuperó o lo decidió: la lectura tardía no lo pisa
        proyecto = db.uno("select * from proyectos where id=:i", i=proyecto_id) if proyecto_id else None
        r = validacion.revisar(x, proyecto, gid, viaje)
        if x.get("error"):
            # Una lectura fallida nunca se aprueba sola
            r["alertas"].insert(0, x["error"])
            r["motivos"].insert(0, "lectura_fallida")
            r["estado"] = "revision"
        # La lectura original tal cual, salvo NaN e infinito, que no son JSON válido: quedan vacíos
        original = {c: None if isinstance(x.get(c), float) and not math.isfinite(x[c]) else x.get(c) for c in extraccion.CAMPOS} \
            | {"confianza": x["confianza"], "dudas": x.get("dudas", [])}
        db.actualizar("gastos", gid, **{c: x[c] for c in extraccion.CAMPOS if c not in ("ciudad", *IMPORTES)},
                      **_importes_guardables(x),
                      confianza=x["confianza"],
                      origen_dato=x["origen_dato"], estado=r["estado"], alertas=r["alertas"], motivos=r["motivos"],
                      total_usd=r["total_usd"], extraido=None if x.get("error") else original)
        revision.subir_version(gid)   # quien abrió el gasto mientras se leía tiene que ver los datos leídos antes de revisar
        eventos.registrar("gasto", gid, "aprobado sin intervención" if r["estado"] == "aprobado_auto" else "enviado a revisión",
                          " ".join(r["alertas"]) or "Todas las validaciones en verde", "reglas de validación")
        if op:
            envios.terminar(op, "completado")


IMPORTES = ("subtotal", "impuesto", "propina", "total")


def _importes_guardables(x: dict) -> dict:
    """Un importe que no es válido (NaN, infinito, total cero o negativo, componente negativo) se guarda vacío:
    a la base no llega un NaN, y la lectura original queda tal cual en `extraido`."""
    salida = {}
    for campo in IMPORTES:
        try:
            valor = dinero.decimal(x[campo], positivo=campo == "total") if x.get(campo) is not None else None
            salida[campo] = None if valor is None or valor < 0 else float(valor)
        except ValueError:
            salida[campo] = None
    return salida


def _vigente(conexion, viaje: dict | None) -> dict | None:
    """El viaje bloqueado y releído; conserva los datos calculados (código, ruta) de la copia que se tenía."""
    fila = db.bloquear_viaje(conexion, viaje["id"]) if viaje else None
    return {**viaje, **fila} if fila else None


def asignar_viaje(gasto_id: int, viaje: dict) -> dict:
    """Enlaza un gasto con su viaje y lo vuelve a validar. Lo que una persona ya aprobó o rechazó no cambia de estado.

    Bloquea el viaje de antes y el de destino (en orden, para que dos asignaciones cruzadas no se esperen entre sí).
    Lanza ValueError con un texto para la persona si el gasto no se puede mover.
    """
    with db.transaccion() as c:
        previo = db.uno("select viaje_id from gastos where id=:i", i=gasto_id)
        if not previo:
            raise ValueError("Ese gasto ya no existe.")
        vigentes = {vid: db.bloquear_viaje(c, vid) for vid in sorted({previo["viaje_id"], viaje["id"]} - {None})}
        g = db.uno("select * from gastos where id=:i", i=gasto_id)
        if g["viaje_id"] != previo["viaje_id"]:
            raise ValueError("El gasto cambió de viaje mientras tanto. Vuelve a consultarlo.")
        if g["estado"] == "procesando":
            if not envios.recuperar_si_atascado(g):
                raise ValueError("El recibo todavía se está leyendo. Inténtalo de nuevo en un momento.")
            g = db.uno("select * from gastos where id=:i", i=gasto_id)
        if not vigentes.get(viaje["id"]):
            raise ValueError("Ese viaje ya no existe.")
        viaje = {**viaje, **vigentes[viaje["id"]]}
        proyecto = db.uno("select * from proyectos where id=:i", i=viaje["proyecto_id"]) if viaje["proyecto_id"] else None
        cambios = {"viaje_id": viaje["id"], "proyecto_id": viaje["proyecto_id"], "viajero_id": viaje["viajero_id"] or g["viajero_id"]}
        if g["estado"] in ("revision", "aprobado_auto"):
            r = validacion.revisar(_campos_de(g), proyecto, gasto_id, viaje)
            if "lectura_fallida" in (db.de_json(g["motivos"], []) or []):
                r["estado"], r["motivos"] = "revision", ["lectura_fallida"] + r["motivos"]
                r["alertas"] = (db.de_json(g["alertas"], []) or [])[:1] + r["alertas"]
            cambios.update(estado=r["estado"], alertas=r["alertas"], motivos=r["motivos"], total_usd=r["total_usd"])
        elif g["estado"] == "aprobado" and g["viaje_id"] != viaje["id"]:
            # Lo aprobado por una persona conserva su estado, pero no puede llevarse a un viaje que no lo admite
            r = validacion.revisar({**_campos_de(g), "confianza": 1.0, "dudas": []}, proyecto, gasto_id, viaje)
            if r["estado"] != "aprobado_auto":
                raise ValueError(f"El viaje {viaje['codigo']} no admite este gasto ya aprobado: " + " ".join(r["alertas"]))
            cambios["total_usd"] = r["total_usd"]
        db.actualizar("gastos", gasto_id, **cambios)
        revision.subir_version(gasto_id)
        if g["documento_id"]:
            db.actualizar("documentos", g["documento_id"], viaje_id=viaje["id"])
        eventos.registrar("gasto", gasto_id, "asignado a viaje", viaje["codigo"])
    return db.uno("select * from gastos where id=:i", i=gasto_id)


def guardar_evidencia(usuario: dict, viaje: dict | None, canal: str, tipo: str, contenido: bytes | None = None,
                      nombre: str = "", texto: str = "") -> int:
    """Audios y notas: se conservan ligados al viaje como evidencia. No originan gasto ni se envían al modelo."""
    ruta = mime = huella = None
    if contenido is not None:
        if len(contenido) > config.MAX_BYTES_SOPORTE:
            raise SoporteRechazado(f"El audio pesa {len(contenido) / 1e6:.1f} MB; el máximo es {config.MAX_BYTES_SOPORTE / 1e6:.1f} MB.")
        clase = tipo_audio(contenido)
        if not clase:
            raise SoporteRechazado("Formato de audio no admitido.")
        mime = clase[0]
        ruta, huella = _guardar(contenido, mime, clase[1])
    doc = db.insertar("documentos", nombre=nombre_visible(nombre or tipo), mime=mime, canal=canal, ruta=ruta, huella=huella,
                      creado=db.ahora(), usuario_id=usuario["id"], viaje_id=viaje["id"] if viaje else None, tipo=tipo,
                      texto=(texto or "")[:2000] or None)
    eventos.registrar("viaje" if viaje else "documento", viaje["id"] if viaje else doc, f"{tipo} guardado como evidencia",
                      (texto or nombre or "")[:120], f"canal: {canal}")
    return doc
