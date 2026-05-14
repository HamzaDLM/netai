import logging
from pathlib import Path

from haystack import tracing
from haystack.tracing.logging_tracer import LoggingTracer
from haystack_integrations.components.generators.google_genai import (
    GoogleGenAIChatGenerator,
)
from rich.traceback import install as install_rich_traceback

from app.core.config import project_settings
from app.core.logging import attach_rotating_file_handler

install_rich_traceback(show_locals=False)  # set True during heavy debugging

HAYSTACK_TRACE_LOG_FILE = Path(__file__).resolve().parents[1] / "haystack_tracing.log"

logging.getLogger("haystack").setLevel(logging.INFO)
attach_rotating_file_handler("haystack", filename=HAYSTACK_TRACE_LOG_FILE)

tracing.tracer.is_content_tracing_enabled = True  # type: ignore

tracing.enable_tracing(  # type: ignore
    LoggingTracer(
        tags_color_strings={
            "haystack.component.input": "\x1b[1;31m",  # bold red
            "haystack.component.name": "\x1b[1;34m",  # bold blue
            "haystack.component.output": "\x1b[1;32m",
        },
    )
)
llm = GoogleGenAIChatGenerator(
    model=project_settings.GEMINI_MODEL,
    generation_kwargs={"temperature": 0.1},
)
