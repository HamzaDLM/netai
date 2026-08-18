import asyncio
from typing import Any

import pytest
from haystack.tools.errors import ToolInvocationError

from app.agent_ui import bind_run_event_sink
from app.tools import _bitbucket_tools_mock, datamodel_tools, probe_tools


def _invoke_with_events(
    tool: Any, **kwargs: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    async def scenario() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with bind_run_event_sink(
            queue,
            asyncio.get_running_loop(),
            run_id="run-test",
            conversation_id="conversation-test",
        ):
            result = await asyncio.to_thread(tool.invoke, **kwargs)
            await asyncio.sleep(0)

        events: list[dict[str, Any]] = []
        while not queue.empty():
            events.append(queue.get_nowait())
        return result, events

    return asyncio.run(scenario())


def test_ping_streams_incremental_simulated_artifact(monkeypatch) -> None:
    monkeypatch.setattr(probe_tools.time, "sleep", lambda _seconds: None)

    result, events = _invoke_with_events(
        probe_tools.ping,
        target="edge-router.example.net",
        count=3,
        interval_ms=50,
    )

    event_types = [event["type"] for event in events]
    assert event_types[0] == "tool_started"
    assert event_types[1] == "artifact_snapshot"
    assert event_types.count("artifact_delta") == 4
    assert event_types[-1] == "tool_completed"
    assert result["simulated"] is True
    assert result["artifact"]["kind"] == "network.ping.v1"


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
def test_visual_probe_examples_complete_artifacts(
    monkeypatch,
    tool: Any,
    kwargs: dict[str, Any],
    artifact_kind: str,
) -> None:
    monkeypatch.setattr(probe_tools.time, "sleep", lambda _seconds: None)

    result, events = _invoke_with_events(tool, **kwargs)

    snapshot = next(event for event in events if event["type"] == "artifact_snapshot")
    final_delta = [event for event in events if event["type"] == "artifact_delta"][-1]
    assert snapshot["artifact"]["kind"] == artifact_kind
    assert snapshot["artifact"]["data"]["simulated"] is True
    assert final_delta["status"] == "completed"
    assert events[-1]["type"] == "tool_completed"
    assert result["artifact"]["kind"] == artifact_kind


def test_probe_target_rejects_shell_syntax() -> None:
    with pytest.raises(ToolInvocationError, match="without shell syntax"):
        probe_tools.ping.invoke(target="router; reboot", count=1)  # type: ignore


def test_config_diff_tool_emits_result_backed_artifact(monkeypatch) -> None:
    monkeypatch.setattr(_bitbucket_tools_mock, "apply_mock_latency", lambda: None)

    result, events = _invoke_with_events(
        _bitbucket_tools_mock.get_recent_device_config_diff,
        device="edge-fw-par-01",
    )

    snapshot = next(event for event in events if event["type"] == "artifact_snapshot")
    final_delta = [event for event in events if event["type"] == "artifact_delta"][-1]
    assert [event["type"] for event in events] == [
        "tool_started",
        "artifact_snapshot",
        "artifact_delta",
        "tool_completed",
    ]
    assert snapshot["artifact"]["kind"] == "config.diff.v1"
    assert snapshot["artifact"]["data"]["arguments"]["device"] == "edge-fw-par-01"
    assert final_delta["status"] == "completed"
    assert final_delta["set"]["config_diff"]["patch"] == result["config_diff"]["patch"]
    assert "\n@@ " in result["config_diff"]["patch"]
    assert "\\n" not in result["config_diff"]["patch"]
    assert "_netai" not in final_delta["set"]


def test_topology_tool_emits_result_backed_artifact() -> None:
    result, events = _invoke_with_events(datamodel_tools.get_topology, site="Paris-DC1")

    snapshot = next(event for event in events if event["type"] == "artifact_snapshot")
    final_delta = [event for event in events if event["type"] == "artifact_delta"][-1]
    assert snapshot["artifact"]["kind"] == "network.topology.v1"
    assert snapshot["artifact"]["data"]["arguments"]["site"] == "Paris-DC1"
    assert final_delta["status"] == "completed"
    assert final_delta["set"]["devices"] == result["devices"]
    assert final_delta["set"]["links"] == result["links"]
    assert events[-1]["type"] == "tool_completed"


def test_topology_tool_accepts_device_scope() -> None:
    result, events = _invoke_with_events(
        datamodel_tools.get_topology,
        site="edge-fw-par-01",
    )

    assert result["scope"] == "edge-fw-par-01"
    assert {device["hostname"] for device in result["devices"]} == {
        "edge-fw-par-01",
        "par-leaf-01",
        "dist-rtr-nyc-01",
    }
    assert result["link_count"] == 2
    assert all(
        "edge-fw-par-01" in {link["a_device"], link["b_device"]}
        for link in result["links"]
    )
    final_delta = [event for event in events if event["type"] == "artifact_delta"][-1]
    assert final_delta["status"] == "completed"


def test_topology_tool_fails_unknown_scope_artifact() -> None:
    result, events = _invoke_with_events(
        datamodel_tools.get_topology,
        site="missing-site",
    )

    assert result["error"] == "No topology data found for scope 'missing-site'."
    assert result["known_sites"]
    final_delta = [event for event in events if event["type"] == "artifact_delta"][-1]
    assert final_delta["status"] == "failed"
    assert final_delta["set"]["error"] == result["error"]


def test_result_backed_artifact_fails_for_tool_error(monkeypatch) -> None:
    monkeypatch.setattr(_bitbucket_tools_mock, "apply_mock_latency", lambda: None)

    result, events = _invoke_with_events(
        _bitbucket_tools_mock.get_recent_device_config_diff,
        device="missing-router",
    )

    final_delta = [event for event in events if event["type"] == "artifact_delta"][-1]
    assert final_delta["status"] == "failed"
    assert final_delta["set"]["error"] == result["error"]
    assert events[-1]["type"] == "tool_completed"
