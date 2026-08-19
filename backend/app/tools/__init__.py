"""Helpers for declaring NetAI's native Haystack tools."""

from __future__ import annotations

from collections.abc import Callable

from haystack.tools import Tool, tool


def apply_mock_latency(
    *,
    min_seconds: float = 0.50,
    max_seconds: float = 5.00,
) -> None:
    """Retained source compatibility for the in-memory connector fixtures.

    Live visual probes model delay with native ``asyncio.sleep``. Other mock
    connectors return immediately so they never block an async Agent run.
    """

    _ = min_seconds, max_seconds


def netai_tool(
    *,
    name: str,
    presentation: dict[str, object] | None = None,
) -> Callable[[Callable[..., object]], Tool]:
    """Declare a Haystack Tool and attach UI/policy metadata.

    Execution, async dispatch, timing, tracing, and lifecycle events belong to
    Haystack's Agent and hooks; this decorator only adds NetAI-specific metadata.
    """

    def decorator(function: Callable[..., object]) -> Tool:
        declared_tool = tool(name=name)(function)
        setattr(declared_tool, "netai_presentation", presentation)
        return declared_tool

    return decorator


__all__ = ["apply_mock_latency", "netai_tool"]
