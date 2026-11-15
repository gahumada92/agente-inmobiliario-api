from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.dependencies import get_inmobiliaria_service
from app.schemas import CapacityRequest, ChatRequest
from app.services.inmobiliaria import InmobiliariaService

router = APIRouter(prefix="/api/v1", tags=["asistente"])
Service = Annotated[InmobiliariaService, Depends(get_inmobiliaria_service)]


@router.post("/purchase-capacity", tags=["finanzas"])
def estimar_capacidad(payload: CapacityRequest, service: Service) -> dict[str, Any]:
    return service.estimar_capacidad(payload)


@router.post("/chat")
def conversar(payload: ChatRequest, service: Service) -> dict[str, str]:
    return service.conversar(payload.mensaje)
