import functools
import inspect
import random
import time
from typing import Any, Awaitable, Callable, TypeVar, Union
from uuid import uuid4

from haystack.tools import tool

from app.agent_ui import (
    ArtifactHandle,
    complete_artifact,
    emit_run_event,
    fail_artifact,
    start_artifact,
)
from app.core.logging import get_business_logger

T = TypeVar("T")
logger = get_business_logger(__name__)
_NETAI_TOOL_METADATA_KEY = "_netai"


def apply_mock_latency(
    *,
    min_seconds: float = 0.50,
    max_seconds: float = 5.00,
) -> None:
    lower = max(0.0, float(min_seconds))
    upper = max(lower, float(max_seconds))
    time.sleep(random.uniform(lower, upper))


def _attach_latency_metadata(result: T, duration_ms: float) -> T:
    if not isinstance(result, dict):
        return result

    metadata = result.get(_NETAI_TOOL_METADATA_KEY)
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        **result,
        _NETAI_TOOL_METADATA_KEY: {
            **metadata,
            "latency_ms": int(round(duration_ms)),
        },
    }  # type: ignore[return-value]


def _bound_arguments(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    """Return named tool arguments for UI metadata, including positional values."""

    try:
        bound = inspect.signature(fn).bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except (TypeError, ValueError):
        return dict(kwargs)


def _start_result_artifact(
    *,
    presentation: dict[str, Any] | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> ArtifactHandle | None:
    """Create an immediate placeholder for tools whose final result is visual."""

    if not presentation or not presentation.get("auto_artifact"):
        return None

    artifact_kind = presentation.get("artifact_kind")
    title = presentation.get("title")
    if not isinstance(artifact_kind, str) or not artifact_kind:
        return None
    if not isinstance(title, str) or not title:
        title = artifact_kind

    return start_artifact(
        kind=artifact_kind,
        title=title,
        schema_version=int(presentation.get("schema_version", 1)),
        data={
            "tool_name": tool_name,
            "arguments": arguments,
        },
        provenance={
            "source": tool_name,
            "effect": presentation.get("effect", "read_only"),
        },
    )


def _finish_result_artifact(handle: ArtifactHandle | None, result: Any) -> None:
    if handle is None:
        return

    if isinstance(result, dict):
        result_values = {
            key: value
            for key, value in result.items()
            if key != _NETAI_TOOL_METADATA_KEY
        }
        error = result_values.get("error")
        if error:
            fail_artifact(handle, str(error))
            return
        complete_artifact(handle, set_values=result_values)
        return

    complete_artifact(handle, set_values={"result": result})


def netai_tool(
    *,
    name: str,
    presentation: dict[str, Any] | None = None,
    **tool_kwargs: Any,
) -> Callable[[Callable[..., T]], Callable[..., Union[T, Awaitable[T]]]]:
    """
    Wraps haystack @tool with logging + timing.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., Union[T, Awaitable[T]]]:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                start: float = time.perf_counter()
                tool_call_id = f"tool_{uuid4().hex}"
                arguments = _bound_arguments(fn, args, kwargs)
                if presentation:
                    emit_run_event(
                        "tool_started",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "arguments": arguments,
                            "presentation": presentation,
                        },
                    )
                result_artifact = _start_result_artifact(
                    presentation=presentation,
                    tool_name=name,
                    arguments=arguments,
                )
                logger.info(
                    "Tool started: %s",
                    name,
                    extra={
                        "event": "tool.start",
                        "tool_name": name,
                        "tool_args": repr(args),
                        "tool_kwargs": repr(kwargs),
                    },
                )

                try:
                    result: T = await fn(*args, **kwargs)
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    if result_artifact:
                        fail_artifact(result_artifact, str(exc))
                    if presentation:
                        emit_run_event(
                            "tool_failed",
                            {
                                "tool_call_id": tool_call_id,
                                "tool_name": name,
                                "duration_ms": int(round(duration_ms)),
                                "error": str(exc),
                            },
                        )
                    raise

                duration_ms = (time.perf_counter() - start) * 1000
                result = _attach_latency_metadata(result, duration_ms)
                _finish_result_artifact(result_artifact, result)
                if presentation:
                    emit_run_event(
                        "tool_completed",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "duration_ms": int(round(duration_ms)),
                        },
                    )
                logger.info(
                    "Tool finished: %s",
                    name,
                    extra={
                        "event": "tool.finish",
                        "tool_name": name,
                        "duration_ms": round(duration_ms, 2),
                        "tool_result": repr(result),
                    },
                )
                return result

            wrapped_tool = tool(name=name, **tool_kwargs)(async_wrapper)  # type: ignore[operator]
            setattr(wrapped_tool, "netai_presentation", presentation)
            return wrapped_tool  # type: ignore[return-value]

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                start: float = time.perf_counter()
                tool_call_id = f"tool_{uuid4().hex}"
                arguments = _bound_arguments(fn, args, kwargs)
                if presentation:
                    emit_run_event(
                        "tool_started",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "arguments": arguments,
                            "presentation": presentation,
                        },
                    )
                result_artifact = _start_result_artifact(
                    presentation=presentation,
                    tool_name=name,
                    arguments=arguments,
                )
                logger.info(
                    "Tool started: %s",
                    name,
                    extra={
                        "event": "tool.start",
                        "tool_name": name,
                        "tool_args": repr(args),
                        "tool_kwargs": repr(kwargs),
                    },
                )

                try:
                    result: T = fn(*args, **kwargs)
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    if result_artifact:
                        fail_artifact(result_artifact, str(exc))
                    if presentation:
                        emit_run_event(
                            "tool_failed",
                            {
                                "tool_call_id": tool_call_id,
                                "tool_name": name,
                                "duration_ms": int(round(duration_ms)),
                                "error": str(exc),
                            },
                        )
                    raise

                duration_ms = (time.perf_counter() - start) * 1000
                result = _attach_latency_metadata(result, duration_ms)
                _finish_result_artifact(result_artifact, result)
                if presentation:
                    emit_run_event(
                        "tool_completed",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "duration_ms": int(round(duration_ms)),
                        },
                    )
                logger.info(
                    "Tool finished: %s",
                    name,
                    extra={
                        "event": "tool.finish",
                        "tool_name": name,
                        "duration_ms": round(duration_ms, 2),
                        "tool_result": repr(result),
                    },
                )
                return result

            wrapped_tool = tool(name=name, **tool_kwargs)(sync_wrapper)  # type: ignore[operator]
            setattr(wrapped_tool, "netai_presentation", presentation)
            return wrapped_tool  # type: ignore[return-value]

    return decorator
