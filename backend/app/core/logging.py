import logging
import logging.config
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_LOGGING_CONFIGURED = False


class _DefaultContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "biz_marker"):
            record.biz_marker = "SYS"
        if not hasattr(record, "event"):
            record.event = "-"
        return True


class BusinessLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:  # type: ignore
        extra = dict(kwargs.get("extra") or {})
        extra.setdefault("biz_marker", "BIZ")
        kwargs["extra"] = extra
        return msg, kwargs


def configure_logging(level: str = "INFO") -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "default_context": {
                    "()": "app.core.logging._DefaultContextFilter",
                }
            },
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(asctime)s | %(levelprefix)s | %(biz_marker)s | %(event)s | %(name)s | %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                    "use_colors": None,
                },
                "access": {
                    "()": "uvicorn.logging.AccessFormatter",
                    "fmt": '%(asctime)s | %(levelprefix)s | SYS | %(client_addr)s - "%(request_line)s" %(status_code)s',
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                    "use_colors": None,
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["default_context"],
                    "stream": "ext://sys.stderr",
                },
                "access": {
                    "class": "logging.StreamHandler",
                    "formatter": "access",
                    "filters": ["default_context"],
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {"handlers": ["default"], "level": level},
            "loggers": {
                "uvicorn": {
                    "handlers": ["default"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["default"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["access"],
                    "level": level,
                    "propagate": False,
                },
            },
        }
    )

    _LOGGING_CONFIGURED = True


def get_business_logger(name: str) -> BusinessLoggerAdapter:
    return BusinessLoggerAdapter(logging.getLogger(name), {})


def attach_rotating_file_handler(
    logger_name: str,
    *,
    filename: Path,
    level: int = logging.DEBUG,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    logger = logging.getLogger(logger_name)
    filename = filename.resolve()

    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename) == filename
        ):
            return

    handler = RotatingFileHandler(
        filename=filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.addFilter(_DefaultContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(biz_marker)s | %(event)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
