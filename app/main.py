"""Composicion de la aplicacion FastAPI."""

import logging
import time
import uuid
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.observability import REQUEST_COUNT, REQUEST_DURATION, configure_logging
from app.routers import assistant, health, properties

configure_logging(settings.log_level)
logger = logging.getLogger("agente_inmobiliario.api")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "API para buscar departamentos, recomendar proyectos y estimar "
        "capacidad de compra en Chile."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def observar_solicitud(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    inicio = time.perf_counter()
    response: Response | None = None
    try:
        response = await call_next(request)
        return response
    finally:
        duracion = time.perf_counter() - inicio
        status_code = response.status_code if response else 500
        path = request.url.path
        REQUEST_COUNT.labels(request.method, path, status_code).inc()
        REQUEST_DURATION.labels(request.method, path).observe(duracion)
        if response is not None:
            response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duracion * 1000, 2),
            },
        )


@app.exception_handler(DomainError)
async def manejar_error_dominio(_: Request, error: DomainError) -> Response:
    return PlainTextResponse(str(error), status_code=error.status_code)


@app.get("/metrics", include_in_schema=False)
def metricas() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(health.router)
app.include_router(properties.router)
app.include_router(assistant.router)
