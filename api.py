"""Punto de entrada compatible para ejecutar ``uvicorn api:app``."""

from app.main import app

__all__ = ["app"]
