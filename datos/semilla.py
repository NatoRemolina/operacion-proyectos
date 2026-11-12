"""Datos de ejemplo: proyectos, viajeros, membresías y catálogo de reglas.

Uso:  python -m datos.semilla           (solo llena tablas vacías)
Las personas, clientes y membresías son inventados.
"""
from app import db

HOY = "2026-11-11"
FAA = "https://www.faa.gov/hazmat/packsafe/airline-passengers-and-batteries"
UNITED = "https://www.united.com/en/us/fly/travel/inflight/basic-economy.html"

REGLAS = [
    # ambito, entidad, tarifa, clave, valor, nota, fuente, confianza
    ("bateria", "", "", "limite_sin_tramite_wh", "100", "Hasta 100 Wh: en cabina, sin trámite. Nunca en bodega.", FAA, "oficial"),
    ("bateria", "", "", "limite_con_aprobacion_wh", "160", "De 101 a 160 Wh: aprobación de la aerolínea y máximo dos de repuesto.", FAA, "oficial"),
    ("aerolinea", "United", "basica", "equipaje_mano", "no", "En rutas nacionales solo artículo personal; en transatlánticas sí incluye.", UNITED, "oficial"),
    ("aerolinea", "United", "basica", "acumula", "no", "Un miembro general sin tarjeta de la aerolínea no acumula millas.", UNITED, "oficial"),
    ("aerolinea", "American", "basica", "equipaje_mano", "si", "Incluye equipaje de mano.", "Respuesta del buscador, 11 nov 2026", "buscador"),
    ("aerolinea", "American", "basica", "acumula", "no", "No acumula millas desde diciembre de 2025.", "https://awardfares.com/blog/aadvantage-business-guide/", "secundaria"),
    ("aerolinea", "American", "", "estatus_maleta_gratis", "si", "El estatus del viajero incluye la primera maleta.", "Por confirmar en la página de la aerolínea", "sin verificar"),
    ("aerolinea", "Delta", "basica", "equipaje_mano", "si", "Incluye equipaje de mano.", "https://thepointsguy.com/glossary/what-is-basic-economy/", "secundaria"),
    ("aerolinea", "Delta", "basica", "acumula", "no", "La tarifa básica no acumula.", "https://thepointsguy.com/glossary/what-is-basic-economy/", "secundaria"),
    ("aerolinea", "Frontier", "basica", "equipaje_mano", "no", "La tarifa más baja solo incluye artículo personal.", "Por confirmar en la página de la aerolínea", "sin verificar"),
    ("aerolinea", "Frontier", "basica", "costo_equipaje_mano", "120", "Estimado ida y vuelta.", "Estimación propia", "sin verificar"),
    ("aerolinea", "Frontier", "basica", "costo_maleta", "110", "Estimado ida y vuelta.", "Estimación propia", "sin verificar"),
    ("aerolinea", "Southwest", "basica", "equipaje_mano", "si", "Incluye equipaje de mano.", "Por confirmar en la página de la aerolínea", "sin verificar"),
    ("aerolinea", "Ryanair", "basica", "equipaje_mano", "no", "Solo bolso pequeño bajo el asiento.", "https://www.which.co.uk/reviews/airlines/article/most-generous-airline-hand-luggage-aF9jK9M1uoMk", "secundaria"),
    ("aerolinea", "easyJet", "basica", "equipaje_mano", "no", "Solo bolso pequeño bajo el asiento.", "https://www.which.co.uk/reviews/airlines/article/most-generous-airline-hand-luggage-aF9jK9M1uoMk", "secundaria"),
    ("hotel", "Marriott", "", "programa", "Marriott Bonvoy", "Acumula solo con reserva directa.", "Análisis previo", "secundaria"),
    ("hotel", "Hilton", "", "programa", "Hilton Honors", "Acumula solo con reserva directa.", "Por confirmar", "sin verificar"),
    ("hotel", "Hyatt", "", "programa", "World of Hyatt", "Acumula solo con reserva directa.", "Por confirmar", "sin verificar"),
    ("supuesto", "", "", "valor_milla_usd", "0.012", "Valor de referencia de una milla en USD.", "Supuesto editable", "supuesto"),
    ("supuesto", "", "", "millas_por_usd", "5", "Millas que acumula un miembro general por dólar.", "Supuesto editable", "supuesto"),
    ("supuesto", "", "", "diferencia_tarifa_cambio", "60", "Diferencia de tarifa esperada al cambiar la fecha (USD).", "Supuesto editable", "supuesto"),
    ("supuesto", "", "", "costo_maleta", "80", "Maleta facturada ida y vuelta cuando no hay dato (USD).", "Supuesto editable", "supuesto"),
    ("supuesto", "", "", "costo_equipaje_mano", "70", "Equipaje de mano ida y vuelta cuando no hay dato (USD).", "Supuesto editable", "supuesto"),
    ("supuesto", "", "", "tasa_EUR_USD", "1.08", "Tasa de referencia para reportar en USD.", "Supuesto editable", "supuesto"),
    ("supuesto", "", "", "tasa_COP_USD", "0.00025", "Tasa de referencia para reportar en USD.", "Supuesto editable", "supuesto"),
]


def sembrar():
    db.crear_tablas()
    if not db.uno("select id from proyectos limit 1"):
        db.insertar("proyectos", nombre="Residencial Summerlin (aéreo)", cliente="Inmobiliaria Ejemplo Oeste",
                    ciudad="Las Vegas", fecha_inicio="2026-12-08", fecha_fin="2026-12-11", moneda="USD")
        db.insertar("proyectos", nombre="Apartamentos Alfama (aéreo)", cliente="Inmobiliaria Ejemplo Ibérica",
                    ciudad="Lisboa", fecha_inicio="2026-12-13", fecha_fin="2026-12-16", moneda="EUR")
    if not db.uno("select id from viajeros limit 1"):
        andres = db.insertar("viajeros", nombre="Andrés Molina", base="Miami", rol="Piloto de dron")
        laura = db.insertar("viajeros", nombre="Laura Pérez", base="Madrid", rol="Piloto de dron")
        db.insertar("membresias", viajero_id=andres, programa="AAdvantage", entidad="American", estatus="Gold")
        db.insertar("membresias", viajero_id=laura, programa="Miles & More", entidad="Lufthansa", estatus="")
        db.insertar("membresias", viajero_id=None, programa="Cuenta de empresa (AAdvantage Business)", entidad="American", estatus="")
    if not db.uno("select id from reglas limit 1"):
        for ambito, entidad, tarifa, clave, valor, nota, fuente, confianza in REGLAS:
            db.insertar("reglas", ambito=ambito, entidad=entidad, tarifa=tarifa, clave=clave, valor=valor,
                        nota=nota, fuente=fuente, confianza=confianza, verificado=HOY)
    from app.servicios import geografia, precios
    precios.cargar_respaldos()
    geografia.cargar()   # aeropuertos, lugares y países del mundo; sin cambios no recarga, pero deja su registro
    asegurar_supuestos()
    from app.servicios import asistente, kpis  # metas de los indicadores y tope del asistente, visibles en Reglas desde el inicio
    kpis.asegurar_metas()
    asistente.asegurar_regla()
    from datos import migracion
    migracion.sembrar_cargos()   # antes de las cuentas: las de demostración nacen con su cargo
    sembrar_cuentas()
    hechos = migracion.migrar()
    crear_vistas()
    migracion.permisos_de_vistas(VISTAS)
    return hechos


# Capa analítica: hechos listos para consultar, con sus dimensiones ya unidas.
# Las usa el catálogo de métricas y sirven tal cual a una herramienta externa de inteligencia de negocio.
VISTAS = {
    "v_h_gasto": """select g.*, p.nombre proyecto, p.ciudad ciudad_proyecto, v.nombre viajero, u.nombre usuario,
                           r.nombre revisor, d.canal, d.mime, d.nombre archivo, vi.estado estado_viaje, vi.ida ida_viaje,
                           coalesce((select c.nombre from usuarios x join cargos c on c.id=x.cargo_id
                                     where x.id=coalesce(vi.usuario_id, g.usuario_id)), 'Sin cargo') cargo
                    from gastos g left join proyectos p on p.id=g.proyecto_id left join viajeros v on v.id=g.viajero_id
                    left join viajes vi on vi.id=g.viaje_id
                    left join usuarios u on u.id=g.usuario_id left join usuarios r on r.id=g.revisado_por
                    left join documentos d on d.id=g.documento_id""",
    "v_h_busqueda": """select s.*, p.nombre proyecto, v.nombre viajero, u.nombre usuario
                       from solicitudes s left join proyectos p on p.id=s.proyecto_id
                       left join viajeros v on v.id=s.viajero_id left join usuarios u on u.id=s.usuario_id""",
    "v_h_decision": """select d.*, s.origen, s.destino, s.ida, s.viajero_id, u.nombre usuario
                       from decisiones d left join solicitudes s on s.id=d.solicitud_id left join usuarios u on u.id=d.usuario_id""",
    "v_h_lectura": "select * from llamadas_modelo",
    "v_h_viaje": """select v.*, s.origen, s.destino, p.nombre proyecto, u.nombre titular, u.rol rol_titular,
                           (select coalesce(sum(g.total_usd),0) from gastos g where g.viaje_id=v.id and g.estado in ('aprobado','aprobado_auto')) gastado_usd,
                           (select coalesce(sum(g.total_usd),0) from gastos g where g.viaje_id=v.id and g.estado='revision') en_revision_usd,
                           (select count(*) from gastos g where g.viaje_id=v.id) gastos,
                           coalesce((select c.nombre from usuarios x join cargos c on c.id=x.cargo_id where x.id=v.usuario_id), 'Sin cargo') cargo
                    from viajes v left join solicitudes s on s.id=v.solicitud_id left join proyectos p on p.id=v.proyecto_id
                    left join usuarios u on u.id=v.usuario_id""",
    "v_h_evento": "select e.*, u.nombre usuario, u.rol from eventos e left join usuarios u on u.id=e.usuario_id",
    "v_h_consulta": """select c.*, s.proyecto_id, s.origen ruta_origen, s.destino ruta_destino, u.nombre usuario
                       from consultas_buscador c left join solicitudes s on s.id=c.solicitud_id
                       left join usuarios u on u.id=c.usuario_id""",
}

SUPUESTOS_NUEVOS = [
    ("modelo_usd_por_millon_entrada", "0.5", "Precio de referencia del modelo de lenguaje por millón de tokens de entrada (USD). Ajustar al precio vigente."),
    ("modelo_usd_por_millon_salida", "3", "Precio de referencia del modelo de lenguaje por millón de tokens de salida (USD). Ajustar al precio vigente."),
    ("viaticos_dia_usd", "75", "Viáticos por día de viaje que se suman al presupuesto (comidas, transporte local, combustible), en USD."),
    ("tolerancia_presupuesto", "0.10", "Margen sobre el presupuesto del viaje antes de mandar un gasto a revisión (0.10 = 10 %)."),
    # Buscador de origen y destino
    ("radio_aeropuertos_km", "400", "Radio para proponer aeropuertos cercanos a un lugar (km en línea recta)."),
    ("maximo_aeropuertos", "4", "Aeropuertos cercanos que se proponen como máximo para un lugar."),
    ("factor_carretera", "1.3", "Distancia por carretera = distancia en línea recta x este factor."),
    ("velocidad_carretera_kmh", "70", "Velocidad media por carretera para estimar el tiempo de traslado (km/h)."),
    ("tope_autocompletado_mes", "60", "Consultas de autocompletado a Google al mes, de las búsquedas del plan. Alcanzado, solo datos locales."),
    ("traslado_minimo_km", "30", "Bajo esta distancia en línea recta entre el aeropuerto y el lugar no se suma traslado (km)."),
    ("traslado_usd_km", "0.35", "Traslado por carretera sin carro de alquiler (taxi o transfer), ida y vuelta (USD por km)."),
    ("combustible_usd_km", "0.12", "Con carro de alquiler el traslado solo suma combustible y peajes, ida y vuelta (USD por km)."),
    ("costo_cambio_usd", "75", "Cargo por cambiar la fecha cuando el buscador dice «Ticket changes for a fee» (USD)."),
    ("tolerancia_precio_aprobacion", "0.05", "Si al aprobar el precio reconfirmado del vuelo sube más que esto (0.05 = 5 %), administración lo confirma antes de aprobar."),
    # Monitoreo del vuelo el día del viaje
    ("monitoreo_horas_antes", "3", "El estado del vuelo se consulta desde estas horas antes de la salida programada hasta la llegada."),
    ("monitoreo_cache_min", "60", "Minutos que se reutiliza una consulta del estado del vuelo antes de pagar otra («Actualizar ahora» la salta)."),
    ("monitoreo_tope_tramo", "6", "Consultas del estado del vuelo como máximo por tramo."),
    ("monitoreo_tope_viaje", "12", "Consultas del estado del vuelo como máximo por viaje en cada sentido (ida o regreso, todos sus tramos)."),
    ("monitoreo_tope_dia", "30", "Consultas en vivo del estado del vuelo como máximo por día, para toda la plataforma."),
    ("monitoreo_retraso_aviso_min", "15", "Retraso que se avisa al viajero (o que crece estos minutos más desde el último aviso)."),
    ("cupo_minimo_monitoreo", "25", "Si al plan del buscador le quedan menos búsquedas que esto, el monitoreo del vuelo se suspende."),
    ("tope_autocompletado_persona_dia", "15", "Consultas de autocompletado a Google por persona y día. Alcanzado, solo datos locales."),
    # Asistente de administración
    ("asesor_usd_dia", "2", "Gasto máximo por día (hora de Bogotá) en sesiones del asesor del asistente, a precio de lista del servicio (USD). "
                            "Alcanzado, el asistente responde sin el asesor y lo dice."),
]


def asegurar_supuestos():
    for clave, valor, nota in SUPUESTOS_NUEVOS:
        if not db.uno("select id from reglas where ambito='supuesto' and clave=:c", c=clave):
            db.insertar("reglas", ambito="supuesto", entidad="", tarifa="", clave=clave, valor=valor, nota=nota,
                        fuente="Supuesto editable", confianza="supuesto", verificado=HOY)


def crear_vistas():
    for nombre, consulta in VISTAS.items():
        db.ejecutar(f"drop view if exists {nombre}")
        db.ejecutar(f"create view {nombre} as {consulta}")


# Cuentas de demostración para ejecutar en local sin configurar nada. Nunca se crean en una base compartida.
# correo, nombre, permiso, contraseña, viajero, cargo
DEMO = [("admin@demo.local", "Administración (demo)", "admin", "demo-admin-2026", None, None),
        ("piloto@demo.local", "Andrés Molina", "colaborador", "demo-piloto-2026", 1, "Pilotaje de dron"),
        ("piloto2@demo.local", "Laura Pérez", "colaborador", "demo-piloto2-2026", 2, "Pilotaje de dron"),
        ("gestor@demo.local", "Gestión de proyecto (demo)", "gestor", "demo-gestor-2026", None, "Producción")]


def _id_cargo(nombre: str | None) -> int | None:
    fila = db.uno("select id from cargos where nombre=:n and activo=1", n=nombre) if nombre else None
    return fila["id"] if fila else None


def sembrar_cuentas():
    import os

    from app import config
    from app.servicios import acceso
    if db.uno("select id from usuarios limit 1"):
        return
    # Cuentas de demostración: solo en local, y en PostgreSQL solo si se piden de forma explícita (entorno con Compose)
    if config.LOCAL and (config.ES_SQLITE or os.getenv("CUENTAS_DEMO") == "1"):
        for correo, nombre, rol, clave, viajero, cargo in DEMO:
            uid = acceso.crear_usuario(correo, nombre, rol, clave, viajero, _id_cargo(cargo))
            if rol == "gestor":   # gestiona el primer proyecto de ejemplo
                db.insertar("proyecto_miembros", usuario_id=uid, proyecto_id=1, papel="gestor", creado=db.ahora())
        return
    # Base compartida: el primer administrador sale de la configuración, una sola vez
    correo, clave = os.getenv("ADMIN_INICIAL_CORREO", ""), os.getenv("ADMIN_INICIAL_CLAVE", "")
    if correo and clave:
        acceso.crear_usuario(correo, "Administración", "admin", clave)
        demo_correo, demo_clave = os.getenv("USUARIO_DEMO_CORREO", ""), os.getenv("USUARIO_DEMO_CLAVE", "")
        if demo_correo and demo_clave:
            acceso.crear_usuario(demo_correo, "Andrés Molina", "colaborador", demo_clave, 1, _id_cargo("Pilotaje de dron"))


if __name__ == "__main__":
    sembrar()
    print("Semilla aplicada.")
