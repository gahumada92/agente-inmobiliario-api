import json
from io import BytesIO

from app.clients.inmotech import InmotechClient


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = BytesIO(body)

    def __enter__(self):
        return self.body

    def __exit__(self, *_):
        return False


def test_cliente_retorna_propiedades_desde_payload(monkeypatch):
    payload = json.dumps({"data": [{"id": 1}, {"id": 2}]}).encode()
    monkeypatch.setattr(
        "app.clients.inmotech.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )

    propiedades = InmotechClient("https://qa.example").listar_propiedades()

    assert propiedades == [{"id": 1}, {"id": 2}]
