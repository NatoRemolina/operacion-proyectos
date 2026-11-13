"""Genera los soportes de ejemplo (ficticios) y sus valores esperados.

Uso:  uvx --with reportlab --with pillow python datos/generar_ejemplos.py
Los comercios, personas y dominios son inventados (todos los correos y enlaces usan dominios `.test`) y cada soporte
lleva el sello visible «FICTICIO · prueba técnica». Los valores esperados sirven para medir la exactitud de la
extracción (`datos/medir_exactitud.py`) y como respuesta guardada cuando no hay clave del modelo. La salida es
siempre la misma: volver a generar no cambia los archivos si no cambia este guion.
"""
import io
import json
from email.message import EmailMessage
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

DIR = Path(__file__).parent / "ejemplos"
DIR.mkdir(exist_ok=True)
SELLO = "FICTICIO · prueba técnica"
ROJO = "#b42318"


def fuente(tam):
    for ruta in ("/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _sellar_imagen(img: Image.Image) -> Image.Image:
    """Franja roja arriba con el sello: se ve aunque la foto esté borrosa."""
    sellada = Image.new("RGB", (img.width, img.height + 44), "#fde8e6")
    sellada.paste(img, (0, 44))
    d = ImageDraw.Draw(sellada)
    d.rectangle((0, 0, img.width - 1, 43), outline=ROJO, width=2)
    d.text((16, 10), SELLO.upper(), fill=ROJO, font=fuente(20))
    return sellada


def _guardar_png(img: Image.Image, destino: Path | None = None) -> bytes:
    info = PngInfo()
    info.add_itxt("Sello", SELLO)   # el mismo sello en los metadatos, para comprobarlo sin leer los píxeles
    salida = io.BytesIO()
    img.save(salida, format="PNG", pnginfo=info)
    if destino:
        destino.write_bytes(salida.getvalue())
    return salida.getvalue()


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
    _guardar_png(_sellar_imagen(img), DIR / nombre)


def _sellar_pagina(c):
    c.saveState()
    c.setFillColorRGB(0.71, 0.14, 0.09)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(540, 760, SELLO)
    c.setFillColorRGB(0.71, 0.14, 0.09, alpha=0.12)
    c.setFont("Helvetica-Bold", 54)
    c.translate(306, 380)
    c.rotate(35)
    c.drawCentredString(0, 0, "FICTICIO")
    c.restoreState()


def factura_pdf(nombre, titulo, *paginas) -> bytes:
    """Un PDF con una página por lista de líneas. Sin compresión: el texto se puede buscar en el archivo."""
    salida = io.BytesIO()
    c = canvas.Canvas(salida, pagesize=letter, invariant=1, pageCompression=0)
    for n, lineas in enumerate(paginas, start=1):
        _sellar_pagina(c)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(72, 720, titulo)
        c.setFont("Helvetica", 11)
        y = 690
        for linea in lineas:
            c.drawString(72, y, linea)
            y -= 18
        if len(paginas) > 1:
            c.setFont("Helvetica", 9)
            c.drawCentredString(306, 40, f"Page {n} of {len(paginas)}")
        c.showPage()
    c.save()
    if nombre:
        (DIR / nombre).write_bytes(salida.getvalue())
    return salida.getvalue()


def correo(nombre, remitente, asunto, fecha, cuerpo, adjuntos=()):
    msg = EmailMessage()
    msg["From"] = remitente
    msg["To"] = "andres.molina@empresa-ejemplo.test"
    msg["Subject"] = f"[{SELLO}] {asunto}"
    msg["Date"] = fecha
    msg.set_content(f"{SELLO}: correo inventado para la prueba técnica.\n\n{cuerpo}")
    for datos, tipo, archivo in adjuntos:
        principal, secundario = tipo.split("/")
        msg.add_attachment(datos, maintype=principal, subtype=secundario, filename=archivo)
    if adjuntos:
        msg.set_boundary(f"limite-{nombre.replace('.', '-')}")   # sin azar: la misma salida en cada corrida
    (DIR / nombre).write_bytes(bytes(msg))


# ---------- fotos de recibos ----------
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
recibo_png("recibo_taxi.png", [
    "DESERT CAB CO.", "Las Vegas, NV", "Cab #1187   Driver 2290", "12/11/2026  06:52 AM", "",
    "From: Desert Sky Hotel", "To:   Harry Reid Intl (LAS)", "",
    "Fare                  23.40", "Tip                    4.00", "TOTAL            USD  27.40", "", "VISA ****4417",
])

# ---------- facturas y confirmaciones en PDF ----------
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
factura_pdf("confirmacion_vuelo.pdf", "Atlantic Gull Airways", [
    "Confirmacion de vuelo / E-ticket receipt", "Booking reference: GQ4LZ8    Issued: 25 Nov 2026", "",
    "Passenger: ANDRES MOLINA",
    "MIA Miami -> LIS Lisboa    Sun 13 Dec 2026    AG 214    Economy",
    "LIS Lisboa -> MIA Miami    Sat 19 Dec 2026    AG 215    Economy", "",
    "Base fare ................................ USD 962.00",
    "Taxes, fees and carrier charges .......... USD 186.30",
    "TOTAL PAID ............................... USD 1,148.30", "",
    "Form of payment: VISA ****4417",
    "Purchased directly from the airline at reservas.atlanticgull.test",
])
factura_pdf("compra_proyecto.pdf", "AeroParts Supply", [
    "2210 Industrial Rd, Las Vegas, NV 89102", "Invoice #APS-50412    Date: 12/09/2026", "",
    "Sold to: Andres Molina (drone crew)", "Project: aerial shoot, Las Vegas", "",
    "2 x Propeller set 9450 (4 pcs) @ 24.99 ... 49.98",
    "1 x Intelligent flight battery 5935 mAh .. 159.00", "",
    "Subtotal ................................. 208.98",
    "Sales tax 8.375% ......................... 17.50",
    "TOTAL (USD) .............................. 226.48", "",
    "Paid: VISA ****4417 at the store counter.",
])
factura_pdf("factura_dos_paginas.pdf", "Tejo Car Hire", [
    "Avenida Infante D. Henrique 3, 1100-000 Lisboa", "Fatura / Invoice FT 2026/3310    Date: 18/12/2026", "",
    "Renter: Andres Molina", "Pick-up: 13/12/2026 10:00    Return: 18/12/2026 09:00", "Vehicle: compact (manual)", "",
    "Day 1  13/12/2026  rental day ............ 42.00",
    "Day 2  14/12/2026  rental day ............ 42.00",
    "Day 3  15/12/2026  rental day ............ 42.00",
    "Day 4  16/12/2026  rental day ............ 42.00",
    "Day 5  17/12/2026  rental day ............ 42.00",
    "Basic insurance (included) ............... 0.00",
    "Mileage: unlimited", "",
    "Continued on page 2 (totals and payment).",
], [
    "Fatura / Invoice FT 2026/3310 (continued)", "",
    "Subtotal (5 days) ........................ 210.00",
    "IVA 23% .................................. 48.30",
    "TOTAL (EUR) .............................. 258.30", "",
    "Paid: VISA ****4417 on 18/12/2026. Booked directly with Tejo Car Hire.",
])

# ---------- correos (.eml) ----------
correo("correo_tiquete.eml", "Reservas <reservas@aerolinea-ejemplo.test>", "Your trip confirmation and receipt - MIA to LAS",
       "Fri, 20 Nov 2026 10:12:00 -0500", """Thank you for your purchase.

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
logo = Image.new("RGB", (220, 60), "#0b4f6c")
ImageDraw.Draw(logo).text((14, 18), "CASA DO TEJO", fill="#ffffff", font=fuente(20))
factura_casa = factura_pdf(None, "Casa do Tejo", [
    "Rua dos Remedios 41, 1100-000 Lisboa", "Fatura / Invoice FT 2026/1187    Date: 17/12/2026", "",
    "Guest: Andres Molina", "Check-in: 13/12/2026    Check-out: 17/12/2026    Nights: 4",
    "Booked directly with the hotel", "",
    "Room   4 x 88.50 ......................... 354.00",
    "IVA 6% ................................... 21.24",
    "TOTAL (EUR) .............................. 375.24", "",
    "Paid: VISA ****4417",
])
correo("reserva_hotel.eml", "Casa do Tejo <reservas@casadotejo.test>", "Fatura FT 2026/1187 - Casa do Tejo",
       "Thu, 17 Dec 2026 11:20:00 +0000",
       "Obrigado pela sua estadia. Segue em anexo a fatura da reserva (4 noites, 13 a 17 de dezembro).\n"
       "Gracias por su estadía. Adjuntamos la factura de la reserva.\n\nCasa do Tejo · https://www.casadotejo.test\n",
       [(_guardar_png(logo), "image/png", "logo_casa_do_tejo.png"),
        (factura_casa, "application/pdf", "fatura_FT_2026_1187.pdf")])

# ---------- confirmación en HTML ----------
(DIR / "confirmacion_hotel.html").write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Booking confirmation - Moab Red Rock Lodge</title>
<style>body {{ font-family: Arial, sans-serif; }} .sello {{ background: #fde8e6; color: {ROJO}; font-weight: bold; padding: 8px; }}</style>
<script>/* Script inofensivo: la plataforma lo descarta al reducir la página a texto. */ console.log("no se ejecuta");</script>
</head><body>
<div class="sello">{SELLO}</div>
<h1>Your booking is confirmed</h1>
<p>Moab Red Rock Lodge &middot; 88 N Main St, Moab, UT 84532</p>
<p>Booked through <a href="https://www.travelnow.test/trips/RR-60318">TravelNow</a> (third-party agency) on 11/28/2026.
Confirmation number RR-60318.</p>
<table>
<tr><th>Guest</th><td>Andres Molina</td></tr>
<tr><th>Stay</th><td>12/21/2026 to 12/23/2026 (2 nights)</td></tr>
<tr><th>Room, 2 x 179.00</th><td>USD 358.00</td></tr>
<tr><th>Taxes and fees</th><td>USD 54.86</td></tr>
<tr><th>Total charged</th><td>USD 412.86</td></tr>
<tr><th>Payment</th><td>Mastercard ****9021 (prepaid on 11/28/2026)</td></tr>
</table>
<p>Questions? <a href="mailto:help@travelnow.test">help@travelnow.test</a></p>
</body></html>
""", encoding="utf-8")


def esperado(comercio, fecha, categoria, subtotal, impuesto, propina, total, moneda, metodo_pago, canal_reserva, ciudad,
             confianza, dudas=()):
    return {"comercio": comercio, "fecha": fecha, "categoria": categoria, "subtotal": subtotal, "impuesto": impuesto,
            "propina": propina, "total": total, "moneda": moneda, "metodo_pago": metodo_pago,
            "canal_reserva": canal_reserva, "ciudad": ciudad, "confianza": confianza, "dudas": list(dudas)}


esperados = {
    "recibo_diner.png": esperado("Strip Diner", "2026-12-09", "comida", 24.50, 2.05, 5.00, 31.55, "USD", "Visa 4417",
                                 None, "Las Vegas", 0.97),
    "recibo_gasolina.png": esperado("Fuel Stop 24", "2026-12-10", "combustible", None, None, None, 38.40, "USD",
                                    "Mastercard 9021", None, "Las Vegas", 0.95),
    "recibo_lisboa.png": esperado("Café do Miradouro", "2026-12-14", "comida", 18.70, 4.30, None, 23.00, "EUR",
                                  "Multibanco", None, "Lisboa", 0.94),
    "recibo_parqueo_borroso.png": esperado("City Park Garage", "2026-12-09", "parqueo_peajes", None, None, None, None,
                                           "USD", "Efectivo", None, "Las Vegas", 0.55, ["total"]),
    "recibo_taxi.png": esperado("Desert Cab Co.", "2026-12-11", "transporte_terrestre", 23.40, None, 4.00, 27.40, "USD",
                                "Visa 4417", None, "Las Vegas", 0.95),
    "factura_hotel.pdf": esperado("Desert Sky Hotel & Suites", "2026-12-11", "hotel", 249.00, 33.32, None, 282.32, "USD",
                                  "Visa 4417", "TravelNow", "Las Vegas", 0.98),
    "factura_alquiler_carro.pdf": esperado("Canyon Car Rental", "2026-12-11", "alquiler_carro", 174.00, 41.76, None,
                                           215.76, "USD", "Visa 4417", "directo", "Las Vegas", 0.98),
    "confirmacion_vuelo.pdf": esperado("Atlantic Gull Airways", "2026-11-25", "vuelo", 962.00, 186.30, None, 1148.30,
                                       "USD", "Visa 4417", "directo", None, 0.97),
    "compra_proyecto.pdf": esperado("AeroParts Supply", "2026-12-09", "compras_proyecto", 208.98, 17.50, None, 226.48,
                                    "USD", "Visa 4417", None, "Las Vegas", 0.97),
    "factura_dos_paginas.pdf": esperado("Tejo Car Hire", "2026-12-18", "alquiler_carro", 210.00, 48.30, None, 258.30,
                                        "EUR", "Visa 4417", "directo", "Lisboa", 0.96),
    "correo_tiquete.eml": esperado("Aerolínea (AA 1851)", "2026-11-20", "vuelo", 521.86, 66.14, None, 588.00, "USD",
                                   "Visa 4417", "directo", None, 0.96),
    "reserva_hotel.eml": esperado("Casa do Tejo", "2026-12-17", "hotel", 354.00, 21.24, None, 375.24, "EUR",
                                  "Visa 4417", "directo", "Lisboa", 0.97),
    "confirmacion_hotel.html": esperado("Moab Red Rock Lodge", "2026-11-28", "hotel", 358.00, 54.86, None, 412.86, "USD",
                                        "Mastercard 9021", "TravelNow", "Moab", 0.96),
}
(DIR / "esperados.json").write_text(json.dumps(esperados, ensure_ascii=False, indent=2) + "\n")
print("Generados", len(esperados), "soportes en", DIR)
