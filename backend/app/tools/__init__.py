import functools
import inspect
import logging
import time
from typing import Any, Awaitable, Callable, TypeVar, Union

from haystack.tools import tool

T = TypeVar("T")
logger = logging.getLogger(__name__)

_PINK_BULLET = "\x1b[95m⦿ TOOLCALL: \x1b[0m"


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
                print(
                    "{} Tool {} running with args={} kwargs={}\n".format(
                        _PINK_BULLET,
                        name,
                        args,
                        kwargs,
                    )
                )

                result: T = await fn(*args, **kwargs)

                duration_ms: float = (time.perf_counter() - start) * 1000
                print(
                    "{} Tool {} finished in {:.2f} ms with result={}\n".format(
                        _PINK_BULLET,
                        name,
                        duration_ms,
                        result,
                    )
                )
                return result

            return tool(name=name, **tool_kwargs)(async_wrapper)  # type: ignore

        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                start: float = time.perf_counter()
                print(
                    "{} Tool {} running with args={} kwargs={}\n".format(
                        _PINK_BULLET,
                        name,
                        args,
                        kwargs,
                    )
                )

                result: T = fn(*args, **kwargs)

                duration_ms: float = (time.perf_counter() - start) * 1000
                print(
                    "{} Tool {} finished in {:.2f} ms with result={}\n".format(
                        _PINK_BULLET,
                        name,
                        duration_ms,
                        result,
                    )
                )
                return result

            return tool(name=name, **tool_kwargs)(sync_wrapper)  # type: ignore

    return decorator
