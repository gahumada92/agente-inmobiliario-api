"""Configuracion centralizada desde variables de entorno."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    api_prefix: str
    inmotech_api_url: str
    openai_model: str
    log_level: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            app_name="API Agente Inmobiliario",
            app_version="1.1.0",
            api_prefix="/api/v1",
            inmotech_api_url=os.getenv("INMOTECH_API_URL", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )


settings = Settings.from_environment()
