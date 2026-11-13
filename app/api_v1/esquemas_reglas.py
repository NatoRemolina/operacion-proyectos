"""Modelos de la API v1 de reglas y supuestos. Contrato en `contracts/api-v1.md`, sección «Reglas y supuestos»."""
from pydantic import BaseModel, ConfigDict, Field


class Regla(BaseModel):
    id: int
    ambito: str = Field(description="aerolinea, hotel, bateria, supuesto, kpi...")
    entidad: str | None = Field(description="A quién aplica: la aerolínea o el programa de hotel; vacío si es general.")
    tarifa: str | None
    clave: str
    valor: str
    numerica: bool = Field(description="El valor es un número: al editarlo, debe seguir siéndolo.")
    nota: str | None
    fuente: str | None = Field(description="Una dirección (http...) o la descripción de dónde sale.")
    confianza: str | None = Field(description="oficial, buscador, secundaria, sin verificar o supuesto.")
    verificado: str | None = Field(description="AAAA-MM-DD de la última verificación o edición.")


class GrupoReglas(BaseModel):
    clave: str = Field(description="aerolinea, hotel, bateria, supuesto, kpi, cuenta_contable u otro ámbito.")
    titulo: str
    reglas: list[Regla]


class Membresia(BaseModel):
    id: int
    titular: str = Field(description="Quien viaja, o «Empresa» si es la cuenta de la empresa.")
    de_empresa: bool
    programa: str | None
    entidad: str | None = Field(description="Dónde aplica (la aerolínea; en hoteles, el programa).")
    estatus: str | None
    ejemplo: bool = Field(description="Dato inventado para la demostración: se rotula «Dato de ejemplo».")


class CatalogoReglas(BaseModel):
    grupos: list[GrupoReglas]
    membresias: list[Membresia] = Field(description="Solo lectura.")


class EdicionRegla(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: str = Field(max_length=500, description="El valor nuevo. Si la regla es numérica, un número de 0 en adelante "
                                                   "(se acepta la coma decimal).")
