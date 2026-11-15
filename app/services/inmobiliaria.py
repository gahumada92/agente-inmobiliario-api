"""Casos de uso del dominio inmobiliario."""

import json
import os
from typing import Any

from openai import APIConnectionError, AuthenticationError, RateLimitError
from strands import Agent

import ia_inmo as dominio

from app.core.exceptions import (
    DependencyUnavailableError,
    NotFoundError,
    RateLimitExceededError,
    UpstreamServiceError,
)
from app.schemas import CapacityRequest, PropertyFilters


class InmobiliariaService:
    """Adapta la logica del asesor para su uso desde HTTP."""

    @staticmethod
    def _parsear_respuesta(texto: str) -> dict[str, Any]:
        if texto.startswith("No pude"):
            raise UpstreamServiceError(texto)
        if texto.startswith("No encontre"):
            raise NotFoundError(texto)
        try:
            return json.loads(texto)
        except json.JSONDecodeError as error:
            raise UpstreamServiceError(
                "La fuente de inventario devolvio una respuesta inesperada."
            ) from error

    def buscar_propiedades(self, filtros: PropertyFilters) -> dict[str, Any]:
        return self._parsear_respuesta(
            dominio.buscar_departamentos(**filtros.model_dump())
        )

    def sugerir_proyectos(self, filtros: PropertyFilters) -> dict[str, Any]:
        return self._parsear_respuesta(dominio.sugerir_proyectos(**filtros.model_dump()))

    def estimar_capacidad(self, payload: CapacityRequest) -> dict[str, Any]:
        return self._parsear_respuesta(
            dominio.estimar_capacidad_compra(**payload.model_dump())
        )

    def resumen_mercado(self, ciudad: str, tipo: str) -> dict[str, Any]:
        return self._parsear_respuesta(dominio.resumen_mercado(ciudad=ciudad, tipo=tipo))

    def readiness(self) -> dict[str, Any]:
        try:
            propiedades = dominio.cargar_propiedades()
        except Exception as error:
            raise DependencyUnavailableError(f"Inventario no disponible: {error}") from error
        return {
            "status": "ready",
            "api_url": dominio.API_URL,
            "propiedades": len(propiedades),
        }

    @staticmethod
    def _crear_agente() -> Agent:
        return Agent(
            model=dominio.modelo,
            system_prompt=dominio.agente.system_prompt,
            tools=[
                dominio.buscar_departamentos,
                dominio.sugerir_proyectos,
                dominio.estimar_capacidad_compra,
                dominio.resumen_mercado,
            ],
        )

    def conversar(self, mensaje: str) -> dict[str, str]:
        if not os.getenv("OPENAI_API_KEY"):
            raise DependencyUnavailableError(
                "OPENAI_API_KEY no esta configurada en el servidor."
            )
        try:
            resultado = self._crear_agente()(mensaje)
        except AuthenticationError as error:
            raise DependencyUnavailableError(
                "La clave de OpenAI configurada en el servidor no es valida."
            ) from error
        except RateLimitError as error:
            raise RateLimitExceededError(
                "OpenAI rechazo la solicitud por limite de uso o facturacion."
            ) from error
        except APIConnectionError as error:
            raise DependencyUnavailableError("No fue posible conectar con OpenAI.") from error
        return {"respuesta": str(resultado).strip()}
