from types import SimpleNamespace

import app.workflows.agent_runner as agent_runner
from app.workflows.utils import AgentTraceExtractor


def test_with_runtime_formatting_prompt_appends_system_message(monkeypatch) -> None:
    monkeypatch.setattr(agent_runner, "FORMATTING_PROMPT", "format-rules")
    base = [SimpleNamespace(text="existing")]

    out = agent_runner._with_runtime_formatting_prompt(base)

    assert len(out) == 2
    assert out[0] is base[0]
    assert "format-rules" in (getattr(out[1], "text", None) or str(out[1]))


def test_tokenize_preserves_whitespace_boundaries() -> None:
    tokens = agent_runner._tokenize("a b")
    assert tokens == ["a ", "b"]


def test_serialized_streaming_callback_is_not_nested() -> None:
    assert "<locals>" not in agent_runner._serialized_streaming_callback.__qualname__


def test_serialized_streaming_callback_pushes_tokens_to_queue() -> None:
    class _DummyQueue:
        def __init__(self) -> None:
            self.items: list[dict[str, str]] = []

        def put_nowait(self, item: dict[str, str]) -> None:
            self.items.append(item)

    class _DummyLoop:
        def call_soon_threadsafe(self, callback, *args) -> None:
            callback(*args)

    queue = _DummyQueue()
    loop = _DummyLoop()
    queue_token = agent_runner._STREAM_QUEUE.set(queue)  # type: ignore[arg-type]
    loop_token = agent_runner._STREAM_LOOP.set(loop)  # type: ignore[arg-type]
    try:
        agent_runner._serialized_streaming_callback(SimpleNamespace(content="hello "))
    finally:
        agent_runner._STREAM_QUEUE.reset(queue_token)
        agent_runner._STREAM_LOOP.reset(loop_token)

    assert queue.items == [{"type": "token", "token": "hello "}]


def test_extract_tool_calls_from_messages_includes_result_payload() -> None:
    extractor = AgentTraceExtractor()
    tool_call = SimpleNamespace(
        id="call-1",
        tool_name="syslog_specialist",
        arguments={"question": "errors"},
    )
    origin = SimpleNamespace(
        id="call-1",
        tool_name="syslog_specialist",
        arguments={"question": "errors"},
    )
    tool_result = SimpleNamespace(origin=origin, result={"ok": True}, error=False)
    message = SimpleNamespace(tool_calls=[tool_call], tool_call_results=[tool_result])

    calls = extractor.extract_tool_calls({"messages": [message]})

    assert len(calls) == 1
    assert calls[0]["name"] == "syslog_specialist"
    assert calls[0]["arguments"] == {"question": "errors"}
    assert calls[0]["result"] == {"ok": True}


def test_build_run_map_extracts_nested_specialist_tool_calls_and_evidence() -> None:
    extractor = AgentTraceExtractor()
    specialist_call = SimpleNamespace(
        id="specialist-1",
        tool_name="zabbix_specialist",
        arguments={"messages": [{"role": "user", "content": "check core-sw-01"}]},
    )
    nested_tool_call = SimpleNamespace(
        id="tool-1",
        tool_name="zabbix_get_host_problems",
        arguments={"hostname_or_ip": "core-sw-01"},
    )
    nested_origin = SimpleNamespace(
        id="tool-1",
        tool_name="zabbix_get_host_problems",
        arguments={"hostname_or_ip": "core-sw-01"},
    )
    nested_tool_result = SimpleNamespace(
        origin=nested_origin,
        result={
            "count": 1,
            "evidence": [
                {"type": "zabbix", "ref": "core-sw-01", "content": "link down"}
            ],
        },
        error=False,
    )
    specialist_origin = SimpleNamespace(
        id="specialist-1",
        tool_name="zabbix_specialist",
        arguments={"messages": [{"role": "user", "content": "check core-sw-01"}]},
    )
    specialist_result = SimpleNamespace(
        origin=specialist_origin,
        result={
            "messages": [
                SimpleNamespace(
                    tool_calls=[nested_tool_call],
                    tool_call_results=[nested_tool_result],
                )
            ]
        },
        error=False,
    )
    message = SimpleNamespace(
        tool_calls=[specialist_call], tool_call_results=[specialist_result]
    )

    run_map = extractor.build_run_map(
        result={"messages": [message]}, total_latency_ms=420
    )

    assert run_map["orchestrator"]["duration_ms"] == 420
    assert run_map["sub_agent_calls"][0]["specialist_name"] == "zabbix"
    assert run_map["sub_agent_calls"][0]["tool_calls"][0]["tool_name"] == (
        "zabbix_get_host_problems"
    )
    assert run_map["sub_agent_calls"][0]["tool_calls"][0]["status"] == "success"
    assert (
        run_map["sub_agent_calls"][0]["tool_calls"][0]["evidence"][0]["content"]
        == "link down"
    )


def test_build_run_map_marks_tool_error_and_propagates_message() -> None:
    extractor = AgentTraceExtractor()
    specialist_call = SimpleNamespace(
        id="specialist-1",
        tool_name="syslog_specialist",
        arguments={"messages": [{"role": "user", "content": "find flaps"}]},
    )
    specialist_origin = SimpleNamespace(
        id="specialist-1",
        tool_name="syslog_specialist",
        arguments={"messages": [{"role": "user", "content": "find flaps"}]},
    )
    specialist_result = SimpleNamespace(
        origin=specialist_origin,
        result={"error_message": "syslog backend timeout", "error_type": "timeout"},
        error=True,
    )
    message = SimpleNamespace(
        tool_calls=[specialist_call], tool_call_results=[specialist_result]
    )

    run_map = extractor.build_run_map(
        result={"messages": [message]}, total_latency_ms=120
    )
    sub = run_map["sub_agent_calls"][0]
    tool = sub["tool_calls"][0]

    assert sub["status"] == "error"
    assert tool["status"] == "error"
    assert tool["error_type"] in {"timeout", "tool_error"}
    assert "timeout" in str(tool["error_message"]).lower()


def test_build_run_map_supports_agent_suffix_specialist_dispatch() -> None:
    extractor = AgentTraceExtractor(
        specialist_descriptions={
            "bitbucket": "Repository-backed configuration analysis."
        }
    )
    specialist_call = SimpleNamespace(
        id="specialist-1",
        tool_name="bitbucket_agent",
        arguments={
            "messages": [{"role": "user", "content": "show file history for edge-01"}]
        },
    )
    nested_tool_call = SimpleNamespace(
        id="tool-1",
        tool_name="bitbucket_get_device_file_info",
        arguments={"device_name": "edge-01"},
    )
    nested_origin = SimpleNamespace(
        id="tool-1",
        tool_name="bitbucket_get_device_file_info",
        arguments={"device_name": "edge-01"},
    )
    nested_tool_result = SimpleNamespace(
        origin=nested_origin,
        result={"file_path": "configs/edge-01.conf"},
        error=False,
    )
    specialist_origin = SimpleNamespace(
        id="specialist-1",
        tool_name="bitbucket_agent",
        arguments={
            "messages": [{"role": "user", "content": "show file history for edge-01"}]
        },
    )
    specialist_result = SimpleNamespace(
        origin=specialist_origin,
        result={
            "messages": [
                SimpleNamespace(
                    tool_calls=[nested_tool_call],
                    tool_call_results=[nested_tool_result],
                )
            ]
        },
        error=False,
    )
    message = SimpleNamespace(
        tool_calls=[specialist_call], tool_call_results=[specialist_result]
    )

    run_map = extractor.build_run_map(
        result={"messages": [message]}, total_latency_ms=210
    )

    assert run_map["orchestrator"]["specialists"] == ["bitbucket"]
    assert run_map["sub_agent_calls"][0]["specialist_name"] == "bitbucket"
    assert run_map["sub_agent_calls"][0]["tool_calls"][0]["tool_name"] == (
        "bitbucket_get_device_file_info"
    )
