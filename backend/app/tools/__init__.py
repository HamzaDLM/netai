import functools
import inspect
import time
from typing import Any, Awaitable, Callable, TypeVar, Union

from haystack.tools import tool

from app.core.logging import get_business_logger

T = TypeVar("T")
logger = get_business_logger(__name__)


def netai_tool(
    *,
    name: str,
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

                result: T = await fn(*args, **kwargs)

                duration_ms: float = (time.perf_counter() - start) * 1000
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

            return tool(name=name, **tool_kwargs)(async_wrapper)  # type: ignore

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                start: float = time.perf_counter()
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

                result: T = fn(*args, **kwargs)

                duration_ms: float = (time.perf_counter() - start) * 1000
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

            return tool(name=name, **tool_kwargs)(sync_wrapper)  # type: ignore

    return decorator
