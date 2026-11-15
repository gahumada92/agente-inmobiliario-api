"""Dependencias inyectables de FastAPI."""

from app.services.inmobiliaria import InmobiliariaService

_inmobiliaria_service = InmobiliariaService()


def get_inmobiliaria_service() -> InmobiliariaService:
    return _inmobiliaria_service
