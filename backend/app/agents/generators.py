from haystack_integrations.components.generators.google_genai import (
    GoogleGenAIChatGenerator,
)
from app.core.config import project_settings

llm = GoogleGenAIChatGenerator(model=project_settings.GEMINI_MODEL)
