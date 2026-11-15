# Capa 2: Dale herramientas — los vinos de tu cava
# El agente ahora puede buscar vinos reales en tu cava.
#
# Ejecutar: python 02_tools.py

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.openai_responses import OpenAIResponsesModel

load_dotenv()

VINOS = json.loads(Path("data/vinos.json").read_text())


@tool
def buscar_vinos(region: str = "", cepa: str = "") -> str:
    """Busca vinos en la cava de 30 vinos chilenos.
    Filtra por región vinícola y/o cepa (tipo de uva).
    Retorna nombre, bodega, región, cepa y notas de cata.
    Usa esta herramienta siempre que el usuario pregunte por un vino específico.

    Args:
        region: Región vinícola para filtrar (ej: Valle del Maipo, Valle de Casablanca). Dejar vacío para no filtrar.
        cepa: Tipo de uva para filtrar (ej: Carménère, Sauvignon Blanc). Dejar vacío para no filtrar.
    """
    resultados = [
        v for v in VINOS
        if (not region or region.lower() in v["region"].lower())
        and (not cepa or cepa.lower() in v["cepa"].lower())
    ]
    if not resultados:
        return "No encontré vinos con esos criterios. Intenta con otra región o cepa."
    # Limitar resultados para no saturar el contexto del modelo
    return json.dumps(resultados[:5], ensure_ascii=False, indent=2)


modelo = OpenAIResponsesModel(model_id=os.getenv("OPENAI_MODEL", "gpt-5-mini"))


_after_tool = False

def callback_handler(**kwargs):
    global _after_tool
    if "reasoningText" in kwargs:
        print(f"💭 {kwargs['reasoningText']}", end="", flush=True)
    if "data" in kwargs:
        if _after_tool:
            print("\n")
            _after_tool = False
        print(kwargs["data"], end="", flush=True)
    if "current_tool_use" in kwargs:
        _after_tool = True
        t = kwargs["current_tool_use"]
        if t.get("name"):
            print(f"\n\n🔧 Herramienta: {t['name']}")
        if t.get("input"):
            print(f"   Parámetros: {t['input']}")


agente = Agent(
    model=modelo,
    callback_handler=callback_handler,
    system_prompt="""Eres un sommelier experto en vinos chilenos. El usuario tiene una cava con 30 vinos chilenos.

Tu rol:
1. Recomendar vinos chilenos según la ocasión, comida o preferencia del usuario.
2. SIEMPRE usar la herramienta buscar_vinos para consultar la cava del usuario antes de recomendar.
3. Basar tus recomendaciones en los datos reales de la cava del usuario, no en conocimiento general.
4. Explicar brevemente por qué recomiendas cada vino (notas de cata, maridaje).
5. Responder siempre en español.
6. Mantener las respuestas concisas — máximo 2-3 párrafos.""",
    tools=[buscar_vinos],
)

PREGUNTA = "¿Qué vino me recomiendas para una cena de mariscos?"
print(f"👩‍💻 Prompt: {PREGUNTA}\n")
print("🤖 Agente: ", end="", flush=True)
if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit("Falta OPENAI_API_KEY. Agregala al entorno o a un archivo .env.")
agente(PREGUNTA)
print("\n")
