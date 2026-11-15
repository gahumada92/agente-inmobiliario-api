import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.openai_responses import OpenAIResponsesModel

load_dotenv()

modelo = OpenAIResponsesModel(model_id=os.getenv("OPENAI_MODEL", "gpt-5-mini"))

agente = Agent(model=modelo)

if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Falta OPENAI_API_KEY. Agregala al entorno o a un archivo .env.")

agente("¿Qué vino me recomiendas para una cena de mariscos?")
