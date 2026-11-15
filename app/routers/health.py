from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.dependencies import get_inmobiliaria_service
from app.services.inmobiliaria import InmobiliariaService

router = APIRouter(tags=["operacion"])
Service = Annotated[InmobiliariaService, Depends(get_inmobiliaria_service)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(service: Service) -> dict[str, Any]:
    return service.readiness()
