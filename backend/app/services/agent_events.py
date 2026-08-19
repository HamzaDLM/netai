"""Request-scoped agent event collection for HTTP and SSE responses."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from time import perf_counter
from uuid import uuid4

from haystack.dataclasses import ToolCall, ToolCallResult

from app.tools.registry import ToolRegistry


def _json_safe(value: object) -> object:
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
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return str(value)


def _decoded_tool_result(result: object) -> object:
    if not isinstance(result, str):
        return _json_safe(result)
    try:
        return _json_safe(json.loads(result))
    except (TypeError, json.JSONDecodeError):
        return result


def _json_safe_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {str(key): _json_safe(item) for key, item in value.items()}


@dataclasses.dataclass(slots=True)
class ToolExecution:
    call_id: str
    tool_name: str
    connector: str
    input_params: dict[str, object]
    started_at: float
    status: str = "running"
    latency_ms: int | None = None
    output: object = None
    error_type: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "tool_call_id": self.call_id,
            "tool_name": self.tool_name,
            "connector": self.connector,
            "input_params": self.input_params,
            "output": self.output,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ArtifactRef:
    id: str
    kind: str
    schema_version: int


class RunObserver:
    """Collect one Agent run's events and optionally publish them to an SSE queue."""

    def __init__(
        self,
        *,
        run_id: str,
        conversation_id: str,
        queue: asyncio.Queue[dict[str, object]] | None = None,
    ) -> None:
        self.run_id = run_id
        self.conversation_id = conversation_id
        self.queue = queue
        self.events: list[dict[str, object]] = []
        self.tool_executions: list[ToolExecution] = []
        self._external_connectors: dict[str, str] = {}
        self._calls: dict[str, ToolExecution] = {}
        self._artifacts: dict[str, ArtifactRef] = {}
        self._sequence = 0
        self._lock = asyncio.Lock()

    def register_external_tools(self, names: set[str], *, connector: str) -> None:
        self._external_connectors.update(dict.fromkeys(names, connector))

    async def emit(
        self,
        event_type: str,
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        async with self._lock:
            self._sequence += 1
            event: dict[str, object] = {
                "type": event_type,
                "event_id": f"evt_{uuid4().hex}",
                "event_sequence": self._sequence,
                "run_id": self.run_id,
                "conversation_id": self.conversation_id,
                "emitted_at": datetime.now(timezone.utc).isoformat(),
                **_json_safe_mapping(dict(payload or {})),
            }
            self.events.append(event)
            if self.queue is not None:
                self.queue.put_nowait(event)
            return event

    async def tool_started(self, call: ToolCall, registry: ToolRegistry) -> None:
        call_id = call.id or f"tool_{uuid4().hex}"
        execution = ToolExecution(
            call_id=call_id,
            tool_name=call.tool_name,
            connector=self._external_connectors.get(
                call.tool_name, registry.connector_for(call.tool_name)
            ),
            input_params=_json_safe_mapping(call.arguments),
            started_at=perf_counter(),
        )
        self._calls[call_id] = execution
        self.tool_executions.append(execution)

        if execution.connector == "internal":
            return

        presentation = registry.presentation_for(call.tool_name)
        await self.emit(
            "tool_started",
            {
                "tool_call_id": call_id,
                "tool_name": call.tool_name,
                "connector": execution.connector,
                "arguments": execution.input_params,
                "presentation": presentation or {},
            },
        )

        if not presentation or not presentation.get("auto_artifact"):
            return
        kind = presentation.get("artifact_kind")
        if not isinstance(kind, str) or not kind:
            return
        title = presentation.get("title")
        schema_version = presentation.get("schema_version", 1)
        artifact = ArtifactRef(
            id=f"art_{uuid4().hex}",
            kind=kind,
            schema_version=schema_version if isinstance(schema_version, int) else 1,
        )
        self._artifacts[call_id] = artifact
        await self.emit(
            "artifact_snapshot",
            {
                "artifact": {
                    "id": artifact.id,
                    "kind": artifact.kind,
                    "schema_version": artifact.schema_version,
                    "status": "running",
                    "title": title if isinstance(title, str) else artifact.kind,
                    "data": {
                        "tool_name": call.tool_name,
                        "arguments": execution.input_params,
                    },
                    "provenance": {
                        "source": call.tool_name,
                        "effect": registry.effect_for(call.tool_name),
                    },
                }
            },
        )

    async def tool_finished(self, result: ToolCallResult) -> None:
        call_id = result.origin.id
        execution = self._calls.get(call_id or "")
        if execution is None:
            execution = next(
                (
                    item
                    for item in reversed(self.tool_executions)
                    if item.tool_name == result.origin.tool_name
                    and item.status == "running"
                ),
                None,
            )
        if execution is None:
            return

        execution.latency_ms = max(
            0, int(round((perf_counter() - execution.started_at) * 1000))
        )
        execution.output = _decoded_tool_result(result.result)
        payload_error = (
            execution.output.get("error")
            if isinstance(execution.output, dict)
            else None
        )
        failed = result.error or bool(payload_error)
        execution.status = "error" if failed else "success"
        if failed:
            execution.error_type = "ToolInvocationError"
            execution.error_message = str(payload_error or result.result)

        if execution.connector == "internal":
            return

        await self.emit(
            "tool_failed" if failed else "tool_completed",
            {
                "tool_call_id": execution.call_id,
                "tool_name": execution.tool_name,
                "connector": execution.connector,
                "duration_ms": execution.latency_ms,
                **(
                    {"error": execution.error_message or "Tool invocation failed"}
                    if failed
                    else {}
                ),
            },
        )

        artifact = self._artifacts.get(execution.call_id)
        if artifact is None:
            return
        artifact_output = execution.output
        if isinstance(artifact_output, dict):
            artifact_output = {
                key: value for key, value in artifact_output.items() if key != "_netai"
            }
        set_values = (
            artifact_output
            if isinstance(artifact_output, dict)
            else {"result": artifact_output}
        )
        if failed:
            set_values = {"error": execution.error_message or "Tool invocation failed"}
        await self.emit(
            "artifact_delta",
            {
                "artifact_id": artifact.id,
                "kind": artifact.kind,
                "schema_version": artifact.schema_version,
                "status": "failed" if failed else "completed",
                "set": set_values,
                "append": {},
            },
        )
