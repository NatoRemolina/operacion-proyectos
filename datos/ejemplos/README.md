# Soportes de ejemplo

Materiales de prueba propios para el reto 2 (gastos con soporte). **Todo es inventado**: comercios, personas, números de
reserva, tarjetas y direcciones. Cada archivo lleva el sello visible **«FICTICIO · prueba técnica»** (franja roja en las
fotos, texto rojo y marca de agua en los PDF, asunto y primera línea en los correos, franja en la página HTML) y todos
los correos y enlaces usan dominios `.test`, reservados para pruebas: no apuntan a nada real.

Se regeneran con:

```
uvx --with reportlab --with pillow python datos/generar_ejemplos.py
```

La salida es siempre la misma: volver a generar no cambia los archivos si no cambia el guion.

## Qué es cada archivo y qué debería leer la plataforma

| Archivo | Formato y canal | Qué es | Lo que debe leer |
|---|---|---|---|
| `recibo_diner.png` | Foto, web o celular | Cena en Las Vegas con propina | Strip Diner · 2026-12-09 · comida · 31,55 USD (impuesto 2,05, propina 5,00) |
| `recibo_gasolina.png` | Foto | Combustible en Las Vegas | Fuel Stop 24 · 2026-12-10 · combustible · 38,40 USD |
| `recibo_lisboa.png` | Foto | Almuerzo en Lisboa, fecha europea (día antes del mes) | Café do Miradouro · 2026-12-14 · comida · 23,00 EUR (IVA 4,30) |
| `recibo_parqueo_borroso.png` | Foto borrosa a propósito | Parqueadero con el total tapado | City Park Garage · 2026-12-09 · parqueo y peajes · **total ilegible**: debe ir a revisión |
| `recibo_taxi.png` | Foto | Taxi del hotel al aeropuerto | Desert Cab Co. · 2026-12-11 · transporte terrestre · 27,40 USD (propina 4,00) |
| `factura_hotel.pdf` | PDF | Factura de hotel reservada por agencia | Desert Sky Hotel & Suites · 2026-12-11 · hotel · 282,32 USD (impuesto 33,32) · canal TravelNow: alerta de fidelización |
| `factura_alquiler_carro.pdf` | PDF | Alquiler de carro en el aeropuerto | Canyon Car Rental · 2026-12-11 · alquiler de carro · 215,76 USD (impuestos 41,76) |
| `confirmacion_vuelo.pdf` | PDF | Confirmación y recibo de un vuelo Miami–Lisboa | Atlantic Gull Airways · 2026-11-25 · vuelo · 1.148,30 USD (impuestos 186,30): comprado antes del viaje |
| `compra_proyecto.pdf` | PDF | Hélices y batería para el dron | AeroParts Supply · 2026-12-09 · compras del proyecto · 226,48 USD (impuesto 17,50) |
| `factura_dos_paginas.pdf` | PDF de 2 páginas | Alquiler de carro en Lisboa: el detalle en la página 1, **el total en la 2** | Tejo Car Hire · 2026-12-18 · alquiler de carro · 258,30 EUR (IVA 48,30) |
| `correo_tiquete.eml` | Correo sin adjuntos, canal correo | Confirmación de tiquete Miami–Las Vegas en el cuerpo del correo | Aerolínea (AA 1851) · 2026-11-20 · vuelo · 588,00 USD (impuestos 66,14) |
| `reserva_hotel.eml` | Correo con un logo PNG y la factura en PDF adjuntos, canal correo | Factura de hotel en Lisboa enviada por el hotel | Debe leer **el PDF adjunto**, no el logo: Casa do Tejo · 2026-12-17 · hotel · 375,24 EUR (IVA 21,24). La ficha muestra remitente y asunto |
| `confirmacion_hotel.html` | Página HTML, canal correo | Confirmación de hotel en Moab reservada por agencia | Moab Red Rock Lodge · 2026-11-28 · hotel · 412,86 USD (impuestos 54,86) · canal TravelNow. Trae un `<script>` inofensivo: la plataforma lo descarta al reducir la página a texto plano, y el original solo se descarga |

`esperados.json` guarda, por archivo, la lectura correcta campo por campo. Se usa de dos formas:

- como **lectura guardada** cuando no hay clave del modelo, para que la demostración funcione igual (se reconoce el
  archivo por su contenido, no por su nombre);
- como **referencia** para medir la exactitud de la lectura real con `datos/medir_exactitud.py`, que escribe
  `docs/exactitud-lectura.md`.

En «Cargar gasto», administración puede procesar las fotos y los PDF como «Soportes de ejemplo» y los `.eml` y `.html`
desde el «Buzón de correo (simulado)».
