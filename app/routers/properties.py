from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_inmobiliaria_service
from app.schemas import PropertyFilters
from app.services.inmobiliaria import InmobiliariaService

router = APIRouter(prefix="/api/v1", tags=["propiedades"])
Service = Annotated[InmobiliariaService, Depends(get_inmobiliaria_service)]


def filtros_propiedades(
    ciudad: str = "",
    tipologia: str = "",
    tipo: str = "",
    entrega: str = "",
    presupuesto_max_uf: float = Query(default=0, ge=0),
    dormitorios_min: int = Query(default=0, ge=0),
    banios_min: int = Query(default=0, ge=0),
    superficie_min: float = Query(default=0, ge=0),
    texto_libre: str = "",
) -> PropertyFilters:
    return PropertyFilters(
        ciudad=ciudad,
        tipologia=tipologia,
        tipo=tipo,
        entrega=entrega,
        presupuesto_max_uf=presupuesto_max_uf,
        dormitorios_min=dormitorios_min,
        banios_min=banios_min,
        superficie_min=superficie_min,
        texto_libre=texto_libre,
    )


Filters = Annotated[PropertyFilters, Depends(filtros_propiedades)]


@router.get("/properties")
def buscar_propiedades(filtros: Filters, service: Service) -> dict[str, Any]:
    return service.buscar_propiedades(filtros)


@router.get("/projects/recommendations", tags=["proyectos"])
def recomendar_proyectos(filtros: Filters, service: Service) -> dict[str, Any]:
    return service.sugerir_proyectos(filtros)


@router.get("/market-summary", tags=["mercado"])
def resumen_mercado(service: Service, ciudad: str = "", tipo: str = "") -> dict[str, Any]:
    return service.resumen_mercado(ciudad=ciudad, tipo=tipo)
