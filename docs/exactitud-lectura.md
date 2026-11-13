# Exactitud de la lectura de soportes

> **Estado: pendiente de corrida.** La medición necesita la clave del modelo; la corre quien integra con
> `python -m datos.medir_exactitud` y este archivo se reescribe con el resultado.

| Dato | Valor |
|---|---|
| Modelo | — |
| Fecha (UTC) | — |
| Soportes | — de 13 en `datos/ejemplos/` |
| Costo estimado | — |

## Cómo se mide

- Cada soporte de `datos/ejemplos/` se lee con el lector real de la plataforma y con la misma preparación que una carga (una confirmación HTML se reduce antes a texto plano).
- Se compara campo por campo con `datos/ejemplos/esperados.json`: comercio (sin tildes, mayúsculas ni signos), fecha, total, moneda, categoría e impuesto, este último solo si el soporte lo trae. Los importes aciertan con una diferencia de hasta 0,01.
- Un total ilegible a propósito (`recibo_parqueo_borroso.png`) solo acierta si el modelo no lo inventa.
- Cada lectura queda en `llamadas_modelo` con uso `exactitud`; el costo se estima con los precios supuestos `modelo_usd_por_millon_entrada` y `modelo_usd_por_millon_salida` de «Reglas y supuestos».
- Topes: como mucho 30 soportes por corrida y un tope de gasto (por omisión 0,50 USD, `--tope-usd`); al llegar a él, lo que falta queda «no medido».
- Sin clave del modelo el guion sale diciendo «sin clave: no se mide» y no escribe nada.

## Por campo

| Campo | Aciertos | Medidos | Exactitud |
|---|---:|---:|---:|
| Comercio | — | — | — |
| Fecha | — | — | — |
| Total | — | — | — |
| Moneda | — | — | — |
| Categoría | — | — | — |
| Impuesto | — | — | — |
| **Total** | — | — | — |

## Por archivo

| Archivo | Comercio | Fecha | Total | Moneda | Categoría | Impuesto | Aciertos |
|---|---|---|---|---|---|---|---:|
| `compra_proyecto.pdf` | — | — | — | — | — | — | — |
| `confirmacion_hotel.html` | — | — | — | — | — | — | — |
| `confirmacion_vuelo.pdf` | — | — | — | — | — | — | — |
| `correo_tiquete.eml` | — | — | — | — | — | — | — |
| `factura_alquiler_carro.pdf` | — | — | — | — | — | — | — |
| `factura_dos_paginas.pdf` | — | — | — | — | — | — | — |
| `factura_hotel.pdf` | — | — | — | — | — | — | — |
| `recibo_diner.png` | — | — | — | — | — | — | — |
| `recibo_gasolina.png` | — | — | — | — | — | — | — |
| `recibo_lisboa.png` | — | — | — | — | — | — | — |
| `recibo_parqueo_borroso.png` | — | — | — | — | — | — | — |
| `recibo_taxi.png` | — | — | — | — | — | — | — |
| `reserva_hotel.eml` | — | — | — | — | — | — | — |
