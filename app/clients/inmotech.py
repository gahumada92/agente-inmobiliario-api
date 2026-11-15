"""Cliente HTTP para el inventario de Inmotech."""

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class InmotechClient:
    api_url: str
    timeout_seconds: int = 20

    def listar_propiedades(self) -> list[dict]:
        request = Request(
            self.api_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        return payload.get("data", [])
