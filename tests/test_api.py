import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import NotFoundError
from app.dependencies import get_inmobiliaria_service
from app.main import app


class FakeInmobiliariaService:
    def readiness(self):
        return {"status": "ready", "api_url": "https://qa.example", "propiedades": 2}

    def buscar_propiedades(self, filtros):
        return {
            "total_resultados": 1,
            "filtros": filtros.model_dump(),
            "resultados": [{"id": 10, "ciudad": "Santiago"}],
        }

    def sugerir_proyectos(self, filtros):
        return {"proyectos_sugeridos": [], "filtros": filtros.model_dump()}

    def estimar_capacidad(self, payload):
        return {"ingreso_mensual_clp": payload.ingreso_mensual_clp}

    def resumen_mercado(self, ciudad, tipo):
        if ciudad == "Sin resultados":
            raise NotFoundError("No encontre propiedades.")
        return {"ciudad": ciudad, "tipo": tipo, "total_propiedades": 2}

    def conversar(self, mensaje):
        return {"respuesta": f"Respuesta para: {mensaje}"}


@pytest.fixture(autouse=True)
def configurar_dependencias():
    app.dependency_overrides[get_inmobiliaria_service] = FakeInmobiliariaService
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_health_responde_ok_y_entrega_request_id(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_ready_usa_servicio_inyectado(client):
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["propiedades"] == 2


def test_busqueda_valida_y_entrega_filtros(client):
    response = client.get("/api/v1/properties?ciudad=Santiago&dormitorios_min=2")

    assert response.status_code == 200
    assert response.json()["filtros"]["ciudad"] == "Santiago"
    assert response.json()["filtros"]["dormitorios_min"] == 2


def test_capacidad_rechaza_ingreso_invalido(client):
    response = client.post("/api/v1/purchase-capacity", json={"ingreso_mensual_clp": 0})

    assert response.status_code == 422


def test_errores_de_dominio_se_traducen_a_http(client):
    response = client.get("/api/v1/market-summary?ciudad=Sin%20resultados")

    assert response.status_code == 404
    assert response.text == "No encontre propiedades."


def test_metricas_prometheus_se_exponen(client):
    client.get("/health")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_requests_total" in response.text
