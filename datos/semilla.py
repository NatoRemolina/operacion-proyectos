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
    from app.servicios import precios
    precios.cargar_respaldos()


if __name__ == "__main__":
    sembrar()
    print("Semilla aplicada.")
