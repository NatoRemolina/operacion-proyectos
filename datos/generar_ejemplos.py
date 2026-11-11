"""Genera los soportes de ejemplo (ficticios) y sus valores esperados.

Uso:  uvx --with reportlab --with pillow python datos/generar_ejemplos.py
Los comercios y personas son inventados. Los valores esperados sirven para medir la
exactitud de la extracción y como respuesta guardada cuando no hay clave del modelo.
"""
import json
from email.message import EmailMessage
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

DIR = Path(__file__).parent / "ejemplos"
DIR.mkdir(exist_ok=True)


def fuente(tam):
    for ruta in ("/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def recibo_png(nombre, lineas, borroso=False, tachar=None):
    alto = 60 + 34 * len(lineas)
    img = Image.new("RGB", (520, alto), "#fbfaf6")
    d = ImageDraw.Draw(img)
    y = 30
    for i, linea in enumerate(lineas):
        d.text((30, y), linea, fill="#222", font=fuente(26 if i == 0 else 20))
        if tachar is not None and i == tachar:
            d.rectangle((250, y - 2, 500, y + 26), fill="#8a8578")
        y += 34
    if borroso:
        img = img.rotate(2.5, expand=True, fillcolor="#d9d5c8").filter(ImageFilter.GaussianBlur(1.6))
    img.save(DIR / nombre)


def factura_pdf(nombre, titulo, lineas):
    c = canvas.Canvas(str(DIR / nombre), pagesize=letter, invariant=1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 720, titulo)
    c.setFont("Helvetica", 11)
    y = 690
    for linea in lineas:
        c.drawString(72, y, linea)
        y -= 18
    c.save()


recibo_png("recibo_diner.png", [
    "STRIP DINER", "3200 S Las Vegas Blvd", "Las Vegas, NV 89109", "12/09/2026  7:42 PM", "",
    "1 Burger combo        16.50", "1 Iced tea             3.50", "1 Pie slice            4.50", "",
    "Subtotal              24.50", "Sales tax 8.375%       2.05", "Tip                    5.00",
    "TOTAL            USD  31.55", "", "VISA ****4417",
])
recibo_png("recibo_gasolina.png", [
    "FUEL STOP 24", "1890 E Tropicana Ave", "Las Vegas, NV", "12/10/2026 08:15", "",
    "Pump 04  Regular", "9.412 gal @ 4.079", "", "TOTAL            USD  38.40", "", "MASTERCARD ****9021",
])
recibo_png("recibo_lisboa.png", [
    "CAFÉ DO MIRADOURO", "Rua de São Pedro 14", "1100-000 Lisboa", "Data: 14/12/2026 13:05", "",
    "2 Menu do dia        17,00", "1 Água 0,5L           1,70", "",
    "Subtotal             18,70", "IVA 23%               4,30", "TOTAL          EUR   23,00", "", "Multibanco",
])
recibo_png("recibo_parqueo_borroso.png", [
    "CITY PARK GARAGE", "Las Vegas, NV", "12/09/2026", "", "Entry 09:10  Exit 17:48",
    "Daily rate", "TOTAL            USD  2?.00", "", "CASH",
], borroso=True, tachar=6)

factura_pdf("factura_hotel.pdf", "Desert Sky Hotel & Suites", [
    "455 Canyon Road, Las Vegas, NV 89109", "Folio / Invoice #DS-20931", "",
    "Guest: Andres Molina", "Arrival: 12/08/2026    Departure: 12/11/2026    Nights: 3",
    "Booked through: TravelNow (third-party agency)", "",
    "Room charge   3 x 83.00 ................. 249.00",
    "Room tax 13.38% ......................... 33.32",
    "TOTAL (USD) ............................. 282.32", "",
    "Payment: VISA ****4417   Invoice date: 12/11/2026",
])
factura_pdf("factura_alquiler_carro.pdf", "Canyon Car Rental", [
    "Harry Reid Intl Airport, Las Vegas, NV", "Rental agreement #CCR-778215", "",
    "Renter: Andres Molina", "Pick-up: 12/08/2026 13:10    Return: 12/11/2026 09:30", "Vehicle: Compact SUV", "",
    "3 days x 58.00 .......................... 174.00",
    "Taxes and airport fees .................. 41.76",
    "TOTAL (USD) ............................. 215.76", "",
    "Paid: VISA ****4417 on 12/11/2026. Booked directly at the counter.",
])

msg = EmailMessage()
msg["From"] = "Reservas <reservas@aerolinea-ejemplo.test>"
msg["To"] = "andres.molina@empresa-ejemplo.test"
msg["Subject"] = "Your trip confirmation and receipt - MIA to LAS"
msg["Date"] = "Fri, 20 Nov 2026 10:12:00 -0500"
msg.set_content("""Thank you for your purchase.

Passenger: ANDRES MOLINA
Record locator: QX7T2L
Issued: November 20, 2026

Miami (MIA) -> Las Vegas (LAS)   Tue, Dec 8, 2026   AA 1851   Main Cabin
Las Vegas (LAS) -> Miami (MIA)   Fri, Dec 11, 2026  AA 1851   Main Cabin

Base fare            USD 521.86
Taxes and fees       USD  66.14
Total paid           USD 588.00
Form of payment: VISA ending 4417
Purchased directly from the airline.
""")
(DIR / "correo_tiquete.eml").write_bytes(bytes(msg))

esperados = {
    "recibo_diner.png": {"comercio": "Strip Diner", "fecha": "2026-12-09", "categoria": "comida", "subtotal": 24.50,
                         "impuesto": 2.05, "propina": 5.00, "total": 31.55, "moneda": "USD", "metodo_pago": "Visa 4417",
                         "canal_reserva": None, "ciudad": "Las Vegas", "confianza": 0.97, "dudas": []},
    "recibo_gasolina.png": {"comercio": "Fuel Stop 24", "fecha": "2026-12-10", "categoria": "combustible", "subtotal": None,
                            "impuesto": None, "propina": None, "total": 38.40, "moneda": "USD",
                            "metodo_pago": "Mastercard 9021", "canal_reserva": None, "ciudad": "Las Vegas",
                            "confianza": 0.95, "dudas": []},
    "recibo_lisboa.png": {"comercio": "Café do Miradouro", "fecha": "2026-12-14", "categoria": "comida", "subtotal": 18.70,
                          "impuesto": 4.30, "propina": None, "total": 23.00, "moneda": "EUR", "metodo_pago": "Multibanco",
                          "canal_reserva": None, "ciudad": "Lisboa", "confianza": 0.94, "dudas": []},
    "recibo_parqueo_borroso.png": {"comercio": "City Park Garage", "fecha": "2026-12-09", "categoria": "parqueo_peajes",
                                   "subtotal": None, "impuesto": None, "propina": None, "total": None, "moneda": "USD",
                                   "metodo_pago": "Efectivo", "canal_reserva": None, "ciudad": "Las Vegas",
                                   "confianza": 0.55, "dudas": ["total"]},
    "factura_hotel.pdf": {"comercio": "Desert Sky Hotel & Suites", "fecha": "2026-12-11", "categoria": "hotel",
                          "subtotal": 249.00, "impuesto": 33.32, "propina": None, "total": 282.32, "moneda": "USD",
                          "metodo_pago": "Visa 4417", "canal_reserva": "TravelNow", "ciudad": "Las Vegas",
                          "confianza": 0.98, "dudas": []},
    "factura_alquiler_carro.pdf": {"comercio": "Canyon Car Rental", "fecha": "2026-12-11", "categoria": "alquiler_carro",
                                   "subtotal": 174.00, "impuesto": 41.76, "propina": None, "total": 215.76,
                                   "moneda": "USD", "metodo_pago": "Visa 4417", "canal_reserva": "directo",
                                   "ciudad": "Las Vegas", "confianza": 0.98, "dudas": []},
    "correo_tiquete.eml": {"comercio": "Aerolínea (AA 1851)", "fecha": "2026-11-20", "categoria": "vuelo",
                           "subtotal": 521.86, "impuesto": 66.14, "propina": None, "total": 588.00, "moneda": "USD",
                           "metodo_pago": "Visa 4417", "canal_reserva": "directo", "ciudad": None,
                           "confianza": 0.96, "dudas": []},
}
(DIR / "esperados.json").write_text(json.dumps(esperados, ensure_ascii=False, indent=2))
print("Generados", len(esperados), "soportes en", DIR)
