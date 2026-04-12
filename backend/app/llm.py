import logging

from haystack import tracing
from haystack.tracing.logging_tracer import LoggingTracer
from haystack_integrations.components.generators.google_genai import (
    GoogleGenAIChatGenerator,
)
from rich.logging import RichHandler  # ← This is the key addition
from rich.traceback import install as install_rich_traceback

from app.core.config import project_settings

install_rich_traceback(show_locals=False)  # set True during heavy debugging

logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",  # RichHandler handles the formatting
    datefmt="[%X]",
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            show_time=True,
            show_path=False,  # set True if you want file:line
            markup=True,
        )
    ],
)

logging.getLogger("haystack").setLevel(logging.DEBUG)

tracing.tracer.is_content_tracing_enabled = True

tracing.enable_tracing(
    LoggingTracer(
        tags_color_strings={
            "haystack.component.input": "\x1b[1;31m",  # bold red
            "haystack.component.name": "\x1b[1;34m",  # bold blue
            "haystack.component.output": "\x1b[1;32m",
        },
    )
)
llm = GoogleGenAIChatGenerator(model=project_settings.GEMINI_MODEL)
