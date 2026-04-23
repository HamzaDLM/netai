import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from haystack import tracing
from haystack.tracing.logging_tracer import LoggingTracer
from haystack_integrations.components.generators.google_genai import (
    GoogleGenAIChatGenerator,
)
from rich.logging import RichHandler  # ← This is the key addition
from rich.traceback import install as install_rich_traceback

from app.core.config import project_settings

install_rich_traceback(show_locals=False)  # set True during heavy debugging

HAYSTACK_TRACE_LOG_FILE = Path(__file__).resolve().parents[1] / "haystack_tracing.log"

file_handler = RotatingFileHandler(
    filename=HAYSTACK_TRACE_LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)

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
        ),
        file_handler,
    ],
)

logging.getLogger("haystack").setLevel(logging.INFO)

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
