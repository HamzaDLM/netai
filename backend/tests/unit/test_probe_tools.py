import json
from typing import cast

import pytest
from haystack.dataclasses import StreamingChunk, ToolCall, ToolCallResult
from haystack.tools import Tool
from haystack.tools.errors import ToolInvocationError

from app.core.config import project_settings
from app.services.agent_events import RunObserver
from app.tools import probe_tools
from app.tools.registry import ToolRegistry


async def _without_delay(_seconds: float) -> None:
    return None


async def _probe_events(
    tool: Tool, **kwargs: object
) -> tuple[dict[str, object], list[dict[str, object]]]:
    events: list[dict[str, object]] = []

    async def callback(chunk: StreamingChunk) -> None:
        event = chunk.meta.get("netai_event")
        if isinstance(event, dict):
            events.append(event)

    result = cast(
        dict[str, object],
        await tool.invoke_async(**kwargs, streaming_callback=callback),
    )
    return result, events


@pytest.mark.anyio
async def test_ping_streams_incremental_artifact(monkeypatch) -> None:
    monkeypatch.setattr(probe_tools.asyncio, "sleep", _without_delay)

    result, events = await _probe_events(
        probe_tools.ping,
        target="edge-router.example.net",
        count=3,
        interval_ms=50,
    )

    assert events[0]["type"] == "artifact_snapshot"
    assert [event["type"] for event in events].count("artifact_delta") == 4
    assert events[-1]["status"] == "completed"
    assert result["simulated"] is True
    artifact = cast(dict[str, object], result["artifact"])
    assert artifact["kind"] == "network.ping.v1"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool", "kwargs", "artifact_kind"),
    [
        (
            probe_tools.traceroute,
            {"target": "edge-router.example.net", "max_hops": 3},
            "network.traceroute.v1",
        ),
        (
            probe_tools.latency_chart,
            {"target": "edge-router.example.net", "points": 5},
            "network.latency-chart.v1",
        ),
    ],
)
async def test_visual_probes_use_native_async_streaming(
    monkeypatch,
    tool: Tool,
    kwargs: dict[str, object],
    artifact_kind: str,
) -> None:
    monkeypatch.setattr(probe_tools.asyncio, "sleep", _without_delay)

    result, events = await _probe_events(tool, **kwargs)

    assert tool.function is None
    assert tool.async_function is not None
    artifact = cast(dict[str, object], events[0]["artifact"])
    assert artifact["kind"] == artifact_kind
    assert events[-1]["status"] == "completed"
    artifact = cast(dict[str, object], result["artifact"])
    assert artifact["kind"] == artifact_kind


@pytest.mark.anyio
async def test_probe_target_rejects_shell_syntax() -> None:
    with pytest.raises(ToolInvocationError, match="without shell syntax"):
        await probe_tools.ping.invoke_async(target="router; reboot", count=1)


async def _observe_tool(
    registry: ToolRegistry,
    tool_name: str,
    arguments: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    tool = registry.get(tool_name)
    assert tool is not None
    observer = RunObserver(run_id="run-test", conversation_id="conversation-test")
    call = ToolCall(tool_name=tool_name, arguments=arguments, id="call-test")
    await observer.tool_started(call, registry)
    result = cast(dict[str, object], await tool.invoke_async(**arguments))
    await observer.tool_finished(
        ToolCallResult(result=json.dumps(result), origin=call, error=False)
    )
    return result, observer.events


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "artifact_kind"),
    [
        (
            "bitbucket_get_recent_device_config_diff",
            {"device": "edge-fw-par-01"},
            "config.diff.v1",
        ),
        (
            "datamodel_get_topology",
            {"site": "edge-fw-par-01"},
            "network.topology.v1",
        ),
    ],
)
async def test_result_backed_visuals_are_emitted_by_agent_hooks(
    tool_name: str,
    arguments: dict[str, object],
    artifact_kind: str,
) -> None:
    registry = ToolRegistry(project_settings)

    result, events = await _observe_tool(registry, tool_name, arguments)

    assert [event["type"] for event in events] == [
        "tool_started",
        "artifact_snapshot",
        "tool_completed",
        "artifact_delta",
    ]
    expected_connector = tool_name.split("_", maxsplit=1)[0]
    assert events[0]["connector"] == expected_connector
    assert events[2]["connector"] == expected_connector
    artifact = cast(dict[str, object], events[1]["artifact"])
    assert artifact["kind"] == artifact_kind
    assert events[-1]["status"] == "completed"
    if tool_name == "datamodel_get_topology":
        event_set = cast(dict[str, object], events[-1]["set"])
        assert event_set["devices"] == result["devices"]
    else:
        event_set = cast(dict[str, object], events[-1]["set"])
        assert event_set["config_diff"] == result["config_diff"]


@pytest.mark.anyio
async def test_empty_topology_scope_produces_failed_artifact() -> None:
    registry = ToolRegistry(project_settings)

    result, events = await _observe_tool(
        registry,
        "datamodel_get_topology",
        {"site": "missing-site"},
    )

    assert "error" in result
    assert events[-2]["type"] == "tool_failed"
    assert events[-1]["status"] == "failed"
    event_set = cast(dict[str, object], events[-1]["set"])
    assert event_set["error"] == result["error"]
