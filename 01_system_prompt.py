# Capa 1: El sommelier básico
# Un agente con un system prompt — solo conocimiento general, sin herramientas.
#
# Ejecutar: python 01_basico.py

import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.openai_responses import OpenAIResponsesModel

load_dotenv()

modelo = OpenAIResponsesModel(model_id=os.getenv("OPENAI_MODEL", "gpt-5-mini"))

agente = Agent(
    model=modelo,
    system_prompt="""Eres un sommelier experto en vinos chilenos.

Tu rol:
1. Recomendar vinos chilenos según la ocasión, comida o preferencia del usuario.
2. Explicar brevemente por qué recomiendas cada vino.
3. Responder siempre en español.
4. Mantener las respuestas concisas — máximo 2-3 párrafos.""",
)

PREGUNTA = "¿Qué vino me recomiendas para una cena de mariscos?"
print(f"👩‍💻 Prompt: {PREGUNTA}\n")
print("🤖 Agente: ", end="", flush=True)
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Falta OPENAI_API_KEY. Agregala al entorno o a un archivo .env.")
agente(PREGUNTA)
print("\n")
