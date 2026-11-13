"""Mide la exactitud de la lectura de soportes contra `datos/ejemplos/esperados.json` y escribe
`docs/exactitud-lectura.md`.

Uso (desde la raíz del repositorio, con la clave del modelo en `.env`):
    python -m datos.medir_exactitud                     # mide y escribe el informe
    python -m datos.medir_exactitud --tope-usd 0.20     # con otro tope de gasto para la corrida
    python -m datos.medir_exactitud --plantilla         # solo escribe el informe vacío, sin llamar al modelo

Lee cada soporte con el lector real (`app/servicios/extraccion.py`), con la misma preparación que una carga. Sin clave
del modelo sale diciendo «sin clave: no se mide» y no escribe nada. Cada lectura pasa por el cliente único del modelo y
queda en `llamadas_modelo` con uso `exactitud`; de ahí sale el costo estimado, con los precios supuestos de
«Reglas y supuestos». Topes: como mucho TOPE_ARCHIVOS soportes y, al alcanzar el tope de gasto, lo que falta queda
«no medido». La base que se usa es la de `.env`: conviene una local o la de pruebas, con las tablas ya creadas.
"""
import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app import config, db
from app.servicios import costo, extraccion, gastos, llm, validacion

DESTINO = config.RAIZ / "docs" / "exactitud-lectura.md"
USO = "exactitud"
CAMPOS = ("comercio", "fecha", "total", "moneda", "categoria", "impuesto")
NOMBRES = {"comercio": "Comercio", "fecha": "Fecha", "total": "Total", "moneda": "Moneda", "categoria": "Categoría",
           "impuesto": "Impuesto"}
IMPORTES = ("total", "impuesto")
TOLERANCIA = Decimal("0.01")
TOPE_ARCHIVOS = 30
TOPE_USD = 0.50


def comparar(campo: str, leido, esperado) -> bool | None:
    """¿Acierta la lectura de un campo? None si no se mide (impuesto que el soporte no trae)."""
    if campo == "impuesto" and esperado is None:
        return None
    if campo in IMPORTES:
        if leido is None or esperado is None:
            return leido is None and esperado is None   # un total ilegible solo acierta si no se inventa
        try:
            return abs(Decimal(str(leido)) - Decimal(str(esperado))) <= TOLERANCIA
        except InvalidOperation:
            return False
    if campo == "comercio":
        return validacion._mismo_comercio(leido, esperado) or (leido is None and esperado is None)
    if campo == "moneda":
        return (leido or "").upper() == (esperado or "").upper()
    return leido == esperado


def _esperados(directorio: Path) -> dict:
    todos = json.loads((directorio / "esperados.json").read_text())
    return {n: todos[n] for n in sorted(todos) if (directorio / n).is_file()}


def _uso_desde(id_antes: int) -> dict:
    """Llamadas, tokens y costo estimado de esta corrida, leídos del registro `llamadas_modelo`."""
    filas = db.todos("select tokens_entrada, tokens_salida from llamadas_modelo where uso=:u and id>:i", u=USO, i=id_antes)
    cat = costo.catalogo()
    p_ent = costo.supuesto(cat, "modelo_usd_por_millon_entrada", 0.5)
    p_sal = costo.supuesto(cat, "modelo_usd_por_millon_salida", 3.0)
    ent = sum(f["tokens_entrada"] or 0 for f in filas)
    sal = sum(f["tokens_salida"] or 0 for f in filas)
    return {"llamadas": len(filas), "tokens_entrada": ent, "tokens_salida": sal,
            "costo_usd": ent / 1e6 * p_ent + sal / 1e6 * p_sal, "precio_entrada": p_ent, "precio_salida": p_sal}


def medir(tope_usd: float = TOPE_USD, directorio: Path = config.DIR_EJEMPLOS) -> dict:
    """Lee cada soporte de ejemplo con el modelo y lo compara con lo esperado. Exige el modelo configurado."""
    id_antes = (db.uno("select coalesce(max(id), 0) m from llamadas_modelo") or {"m": 0})["m"]
    archivos, detenido = [], False
    for nombre, esperado in list(_esperados(directorio).items())[:TOPE_ARCHIVOS]:
        if detenido or _uso_desde(id_antes)["costo_usd"] >= tope_usd:
            detenido = True
            archivos.append({"nombre": nombre, "medido": False, "campos": {}, "error": None})
            continue
        try:
            contenido, mime, _ = gastos.preparar((directorio / nombre).read_bytes(), nombre)
            lectura = extraccion.extraer(contenido, mime, nombre, uso=USO)
        except gastos.SoporteRechazado as e:
            lectura = {c: None for c in extraccion.CAMPOS} | {"error": str(e)}
        campos = {c: {"ok": comparar(c, lectura.get(c), esperado.get(c)), "leido": lectura.get(c),
                      "esperado": esperado.get(c)} for c in CAMPOS}
        archivos.append({"nombre": nombre, "medido": True, "campos": campos, "error": lectura.get("error")})
    return {"modelo": config.MODELO_NOMBRE, "fecha": datetime.now(UTC).date().isoformat(), "tope_usd": tope_usd,
            "detenido": detenido, "archivos": archivos, "uso": _uso_desde(id_antes)}


# ---------- informe ----------
def _pct(aciertos: int, medidos: int) -> str:
    return f"{aciertos / medidos:.1%}".replace(".", ",") if medidos else "—"


def _usd(valor: float, cifras: int = 4) -> str:
    return f"{valor:.{cifras}f}".replace(".", ",") + " USD"


def _celda(campo: dict | None) -> str:
    if campo is None:
        return "—"
    if campo["ok"] is None:
        return "no aplica"
    if campo["ok"]:
        return "✓"
    leido = "nada" if campo["leido"] is None else str(campo["leido"]).replace("|", "/")
    return f"✗ leyó {leido}"


def informe(resultado: dict | None, directorio: Path = config.DIR_EJEMPLOS) -> str:
    """El informe en Markdown. Sin resultado, la estructura con la nota «pendiente de corrida»."""
    nombres = list(_esperados(directorio))[:TOPE_ARCHIVOS]
    archivos = {a["nombre"]: a for a in (resultado or {}).get("archivos", [])}
    medidos = [a for a in archivos.values() if a["medido"]]
    por_campo = {c: [a["campos"][c]["ok"] for a in medidos if a["campos"][c]["ok"] is not None] for c in CAMPOS}
    aciertos, total = sum(sum(v) for v in por_campo.values()), sum(len(v) for v in por_campo.values())
    uso = (resultado or {}).get("uso")

    lineas = ["# Exactitud de la lectura de soportes", ""]
    if resultado is None:
        lineas += ["> **Estado: pendiente de corrida.** La medición necesita la clave del modelo; la corre quien integra con",
                   "> `python -m datos.medir_exactitud` y este archivo se reescribe con el resultado.", ""]
    else:
        lineas += [f"Resultado: **{aciertos} de {total} campos** leídos bien ({_pct(aciertos, total)}).", ""]
        if resultado["detenido"]:
            lineas += [f"> La corrida se detuvo al llegar al tope de gasto ({_usd(resultado['tope_usd'], 2)}): "
                       "lo que falta quedó «no medido».", ""]
    lineas += ["| Dato | Valor |", "|---|---|",
               f"| Modelo | {resultado['modelo'] if resultado else '—'} |",
               f"| Fecha (UTC) | {resultado['fecha'] if resultado else '—'} |",
               f"| Soportes | {len(medidos) if resultado else '—'} de {len(nombres)} en `datos/ejemplos/` |",
               "| Costo estimado | " + (f"{_usd(uso['costo_usd'])} ({uso['llamadas']} llamadas, {uso['tokens_entrada']} tokens "
                                        f"de entrada y {uso['tokens_salida']} de salida)" if uso and uso["llamadas"] else
                                        "no disponible: la base no registró llamadas" if uso else "—") + " |", ""]
    lineas += ["## Cómo se mide", "",
               "- Cada soporte de `datos/ejemplos/` se lee con el lector real de la plataforma y con la misma preparación "
               "que una carga (una confirmación HTML se reduce antes a texto plano).",
               "- Se compara campo por campo con `datos/ejemplos/esperados.json`: comercio (sin tildes, mayúsculas ni "
               "signos), fecha, total, moneda, categoría e impuesto, este último solo si el soporte lo trae. Los importes "
               "aciertan con una diferencia de hasta 0,01.",
               "- Un total ilegible a propósito (`recibo_parqueo_borroso.png`) solo acierta si el modelo no lo inventa.",
               f"- Cada lectura queda en `llamadas_modelo` con uso `{USO}`; el costo se estima con los precios supuestos "
               "`modelo_usd_por_millon_entrada` y `modelo_usd_por_millon_salida` de «Reglas y supuestos».",
               f"- Topes: como mucho {TOPE_ARCHIVOS} soportes por corrida y un tope de gasto (por omisión "
               f"{_usd(TOPE_USD, 2)}, `--tope-usd`); al llegar a él, lo que falta queda «no medido».",
               "- Sin clave del modelo el guion sale diciendo «sin clave: no se mide» y no escribe nada.", ""]
    lineas += ["## Por campo", "", "| Campo | Aciertos | Medidos | Exactitud |", "|---|---:|---:|---:|"]
    for c in CAMPOS:
        v = por_campo[c]
        lineas.append(f"| {NOMBRES[c]} | {sum(v) if resultado else '—'} | {len(v) if resultado else '—'} | "
                      f"{_pct(sum(v), len(v)) if resultado else '—'} |")
    lineas.append(f"| **Total** | {aciertos if resultado else '—'} | {total if resultado else '—'} | "
                  f"{_pct(aciertos, total) if resultado else '—'} |")
    lineas += ["", "## Por archivo", "",
               "| Archivo | " + " | ".join(NOMBRES[c] for c in CAMPOS) + " | Aciertos |",
               "|---|" + "---|" * len(CAMPOS) + "---:|"]
    for nombre in nombres:
        a = archivos.get(nombre)
        if not a or not a["medido"]:
            relleno = "no medido" if a else "—"
            lineas.append(f"| `{nombre}` | " + " | ".join([relleno] * len(CAMPOS)) + f" | {relleno} |")
            continue
        ok = [x["ok"] for x in a["campos"].values() if x["ok"] is not None]
        celdas = " | ".join(_celda(a["campos"][c]) for c in CAMPOS)
        nota = f" (error: {a['error'][:80]})" if a["error"] else ""
        lineas.append(f"| `{nombre}` | {celdas} | {sum(ok)} de {len(ok)}{nota} |")
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Mide la exactitud de la lectura de soportes contra los esperados.")
    p.add_argument("--destino", type=Path, default=DESTINO)
    p.add_argument("--tope-usd", type=float, default=TOPE_USD, help="Gasto máximo de la corrida, en USD.")
    p.add_argument("--plantilla", action="store_true", help="Solo escribe el informe vacío, sin llamar al modelo.")
    args = p.parse_args(argv)
    if args.plantilla:
        args.destino.write_text(informe(None))
        return 0
    if config.modo()["extraccion"] != "en vivo":
        sys.exit("sin clave: no se mide")
    if not llm.activo():
        sys.exit("el modelo configurado no pasa por el cliente que registra las llamadas: no se mide")
    resultado = medir(args.tope_usd)
    args.destino.write_text(informe(resultado))
    print(f"Informe escrito en {args.destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
