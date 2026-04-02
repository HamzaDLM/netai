import logging
import random
from dataclasses import dataclass
from typing import Any

from app.core.config import project_settings

logger = logging.getLogger(__name__)


def _safe_call(target: Any, method_name: str, **kwargs: Any) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return None
    try:
        return method(**kwargs)
    except Exception:
        logger.debug("Langfuse call failed: %s", method_name, exc_info=True)
        return None


@dataclass(slots=True)
class LangfuseObservation:
    raw: Any = None

    def span(
        self,
        name: str,
        *,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "LangfuseObservation":
        child = _safe_call(
            self.raw,
            "start_observation",
            name=name,
            as_type="span",
            input=input,
            output=output,
            metadata=metadata,
        )
        return LangfuseObservation(child)

    def generation(
        self,
        name: str,
        *,
        model: str | None = None,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "LangfuseObservation":
        child = _safe_call(
            self.raw,
            "start_observation",
            name=name,
            as_type="generation",
            model=model,
            input=input,
            output=output,
            metadata=metadata,
        )
        return LangfuseObservation(child)

    def event(
        self,
        name: str,
        *,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        _safe_call(
            self.raw,
            "start_observation",
            name=name,
            as_type="event",
            input=input,
            output=output,
            metadata=metadata,
        )

    def update(
        self,
        *,
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        _safe_call(
            self.raw,
            "update",
            input=input,
            output=output,
            metadata=metadata,
        )

    def end(
        self,
        *,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if output is not None or metadata is not None:
            self.update(output=output, metadata=metadata)
        _safe_call(self.raw, "end")


class LangfuseClientWrapper:
    def __init__(self) -> None:
        self._client: Any | None = None
        self._enabled = False
        self._boot()

    def _boot(self) -> None:
        if not project_settings.LANGFUSE_ENABLED:
            logger.info("Langfuse disabled via LANGFUSE_ENABLED=false")
            return
        if (
            not project_settings.LANGFUSE_PUBLIC_KEY
            or not project_settings.LANGFUSE_SECRET_KEY
        ):
            logger.info("Langfuse keys missing; tracing disabled")
            return

        try:
            from langfuse import Langfuse  # type: ignore

            self._client = Langfuse(
                public_key=project_settings.LANGFUSE_PUBLIC_KEY,
                secret_key=project_settings.LANGFUSE_SECRET_KEY,
                host=project_settings.LANGFUSE_BASE_URL,
            )
            self._enabled = True
            logger.info("Langfuse tracing enabled")
        except Exception:
            logger.exception("Failed to initialize Langfuse; tracing disabled")
            self._client = None
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._client is not None

    def start_trace(
        self,
        name: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LangfuseObservation:
        if not self.enabled:
            return LangfuseObservation()

        if project_settings.LANGFUSE_SAMPLE_RATE < 1.0:
            if random.random() > project_settings.LANGFUSE_SAMPLE_RATE:
                return LangfuseObservation()

        # In Langfuse SDK v3, traces are represented by observation trees.
        # We create a root span observation and attach session/user context as metadata.
        trace_metadata: dict[str, Any] = dict(metadata or {})
        if user_id is not None:
            trace_metadata["user_id"] = user_id
        if session_id is not None:
            trace_metadata["session_id"] = session_id

        raw_trace = _safe_call(
            self._client,
            "start_observation",
            name=name,
            as_type="span",
            input=input,
            metadata=trace_metadata,
        )
        return LangfuseObservation(raw_trace)

    def flush(self) -> None:
        if not self.enabled:
            return
        _safe_call(self._client, "flush")

    def shutdown(self) -> None:
        if not self.enabled:
            return
        # Flush is the only guaranteed call we rely on across SDK variants.
        _safe_call(self._client, "flush")


langfuse_client = LangfuseClientWrapper()
