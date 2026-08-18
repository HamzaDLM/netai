"""Request-scoped event publishing for live agent and tool UI updates.

The agent currently executes synchronous infrastructure tools in worker threads.
Context variables are therefore used to carry one request's event sink into those
threads without making UI callbacks part of the LLM-visible tool schema.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


@dataclasses.dataclass(frozen=True, slots=True)
class RunEventSink:
    queue: asyncio.Queue[dict[str, Any]]
    loop: asyncio.AbstractEventLoop
    run_id: str
    conversation_id: str


@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactHandle:
    id: str
    kind: str
    schema_version: int
    title: str


_RUN_EVENT_SINK: ContextVar[RunEventSink | None] = ContextVar(
    "netai_run_event_sink", default=None
)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_safe(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json"))
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


@contextmanager
def bind_run_event_sink(
    queue: asyncio.Queue[dict[str, Any]],
    loop: asyncio.AbstractEventLoop,
    *,
    run_id: str,
    conversation_id: str,
) -> Iterator[None]:
    """Bind an event queue to the current agent run and any copied thread context."""

    token = _RUN_EVENT_SINK.set(
        RunEventSink(
            queue=queue,
            loop=loop,
            run_id=run_id,
            conversation_id=conversation_id,
        )
    )
    try:
        yield
    finally:
        _RUN_EVENT_SINK.reset(token)


def emit_run_event(event_type: str, payload: Mapping[str, Any] | None = None) -> None:
    """Publish an event when a run sink is present; otherwise remain a no-op."""

    sink = _RUN_EVENT_SINK.get()
    if sink is None:
        return

    event = {
        "type": event_type,
        "event_id": f"evt_{uuid4().hex}",
        "run_id": sink.run_id,
        "conversation_id": sink.conversation_id,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        **_json_safe(dict(payload or {})),
    }
    sink.loop.call_soon_threadsafe(sink.queue.put_nowait, event)


def start_artifact(
    *,
    kind: str,
    title: str,
    data: Mapping[str, Any],
    schema_version: int = 1,
    provenance: Mapping[str, Any] | None = None,
) -> ArtifactHandle:
    handle = ArtifactHandle(
        id=f"art_{uuid4().hex}",
        kind=kind,
        schema_version=schema_version,
        title=title,
    )
    emit_run_event(
        "artifact_snapshot",
        {
            "artifact": {
                "id": handle.id,
                "kind": handle.kind,
                "schema_version": handle.schema_version,
                "status": "running",
                "title": handle.title,
                "data": dict(data),
                "provenance": dict(provenance or {}),
            }
        },
    )
    return handle


def update_artifact(
    handle: ArtifactHandle,
    *,
    set_values: Mapping[str, Any] | None = None,
    append_values: Mapping[str, list[Any]] | None = None,
    status: str = "running",
) -> None:
    """Emit a small merge/append delta for an existing artifact."""

    emit_run_event(
        "artifact_delta",
        {
            "artifact_id": handle.id,
            "kind": handle.kind,
            "schema_version": handle.schema_version,
            "status": status,
            "set": dict(set_values or {}),
            "append": dict(append_values or {}),
        },
    )


def complete_artifact(
    handle: ArtifactHandle,
    *,
    set_values: Mapping[str, Any] | None = None,
) -> None:
    update_artifact(handle, set_values=set_values, status="completed")


def fail_artifact(handle: ArtifactHandle, message: str) -> None:
    update_artifact(
        handle,
        set_values={"error": message},
        status="failed",
    )
