"""Modelos de la API v1 de usuarios, cargos y la cuenta propia. Contrato en `contracts/api-v1.md`."""
from pydantic import BaseModel, ConfigDict, Field

from .esquemas import Persona, Rol


# ---------- entrada ----------
class NuevaCuenta(BaseModel):
    """La contraseña inicial la escribe administración y nunca se devuelve. Toda cuenta nueva recibe su perfil de viajero."""
    model_config = ConfigDict(extra="forbid")
    correo: str = Field(max_length=200)
    nombre: str = Field("", max_length=200, description="Vacío usa el correo.")
    rol: str = Field(max_length=20, description="colaborador, gestor o admin.")
    clave: str = Field(max_length=200, description="10 caracteres o más.")
    cargo_id: int | None = Field(None, ge=0, description="Un cargo activo, o null (0 también es «sin cargo»).")


class CambioRol(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rol: str = Field(max_length=20, description="colaborador, gestor o admin.")


class CambioCargo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cargo_id: int | None = Field(ge=0, description="Un cargo activo, o null para quitarlo.")


class CambioProyectos(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proyectos_ids: list[int] = Field(max_length=500, description="Los proyectos que gestiona; reemplaza los anteriores.")


class CambioEstadoCuenta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activo: bool


class NuevaClave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clave: str = Field(max_length=200, description="10 caracteres o más.")


class NuevoCargo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombre: str = Field(max_length=200, description="Al menos 3 letras; se guardan hasta 60 caracteres.")


class CambioCargoCatalogo(BaseModel):
    """Renombrar, activar o desactivar. Lo que no se manda no cambia. Un cargo nunca se borra."""
    model_config = ConfigDict(extra="forbid")
    nombre: str | None = Field(None, max_length=200)
    activo: bool | None = None


# ---------- salida ----------
class Referencia(BaseModel):
    id: int
    nombre: str


class EstadoTelegram(BaseModel):
    vinculado: bool
    usuario: str | None = Field(description="Alias de Telegram del chat vinculado, si lo tiene.")


class Usuario(BaseModel):
    id: int
    codigo: str
    correo: str
    nombre: str
    rol: Rol
    rol_texto: str
    cargo: Referencia | None = Field(description="Qué hace en la empresa. No da permisos.")
    proyectos: list[Referencia] = Field(description="Proyectos que gestiona (solo cuentan con el permiso de gestor).")
    activo: bool
    telegram: EstadoTelegram
    ultima_sesion: str | None = Field(description="Última actividad de una sesión abierta (UTC).")
    creado: str | None


class ListaUsuarios(BaseModel):
    items: list[Usuario]
    siguiente: str | None


class ResultadoUsuario(BaseModel):
    usuario: Usuario
    mensaje: str = Field(description="Lo que pasó, en lenguaje claro.")


class Cargo(BaseModel):
    id: int
    nombre: str
    activo: bool
    personas: int = Field(description="Cuentas que tienen este cargo.")


class ListaCargos(BaseModel):
    items: list[Cargo] = Field(description="El catálogo completo, sin paginar, por nombre.")


# ---------- mi cuenta ----------
class TelegramPropio(EstadoTelegram):
    canal_activo: bool = Field(description="El bot de Telegram está configurado en esta instalación. En producción hoy está apagado.")


class MiCuenta(BaseModel):
    persona: Persona
    rol_texto: str
    telegram: TelegramPropio


class CambioMiClave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actual: str = Field(max_length=200)
    nueva: str = Field(max_length=200, description="10 caracteres o más y distinta de la actual.")


class ClaveCambiada(BaseModel):
    csrf_token: str = Field(description="La sesión se renueva al cambiar la contraseña: el token CSRF anterior deja de servir.")
    mensaje: str


class VinculoTelegram(BaseModel):
    codigo: str = Field(description="Código de un solo uso para escribir en el chat del bot: /start <codigo>.")
    enlace: str | None = Field(description="Enlace que abre el chat del bot con el código, si el bot tiene nombre configurado.")
    minutos: int = Field(description="Minutos de validez del código.")
