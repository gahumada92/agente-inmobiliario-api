"""Modelos de entrada y filtros de la API."""

from pydantic import BaseModel, Field


class PropertyFilters(BaseModel):
    ciudad: str = ""
    tipologia: str = ""
    tipo: str = ""
    entrega: str = ""
    presupuesto_max_uf: float = Field(default=0, ge=0)
    dormitorios_min: int = Field(default=0, ge=0)
    banios_min: int = Field(default=0, ge=0)
    superficie_min: float = Field(default=0, ge=0)
    texto_libre: str = ""


class CapacityRequest(BaseModel):
    ingreso_mensual_clp: float = Field(gt=0, description="Ingreso mensual en CLP")
    ciudad: str = ""
    tipologia: str = ""
    dormitorios_min: int = Field(default=0, ge=0)


class ChatRequest(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2_000)
