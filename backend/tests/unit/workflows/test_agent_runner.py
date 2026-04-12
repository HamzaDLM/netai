from types import SimpleNamespace

import app.workflows.agent_runner as agent_runner


def test_with_runtime_formatting_prompt_appends_system_message(monkeypatch) -> None:
    monkeypatch.setattr(agent_runner, "FORMATTING_PROMPT", "format-rules")
    base = [SimpleNamespace(text="existing")]

    out = agent_runner._with_runtime_formatting_prompt(base)

    assert len(out) == 2
    assert out[0] is base[0]
    assert "format-rules" in (getattr(out[1], "text", None) or str(out[1]))


def test_extract_answer_prefers_replies_field() -> None:
    result = {
        "replies": [SimpleNamespace(text="final answer")],
        "messages": [SimpleNamespace(text="fallback")],
    }

    assert agent_runner._extract_answer(result) == "final answer"


def test_extract_tool_calls_from_messages_includes_result_payload() -> None:
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

    calls = agent_runner._extract_tool_calls({"messages": [message]})

    assert len(calls) == 1
    assert calls[0]["name"] == "syslog_specialist"
    assert calls[0]["arguments"] == {"question": "errors"}
    assert calls[0]["result"] == {"ok": True}


def test_extract_specialist_name_suffix_handling() -> None:
    assert agent_runner._extract_specialist_name("syslog_specialist") == "syslog"
    assert agent_runner._extract_specialist_name("zabbix") == "zabbix"
    assert agent_runner._extract_specialist_name(None) == "unknown"


def test_tokenize_preserves_whitespace_boundaries() -> None:
    tokens = agent_runner._tokenize("a b")
    assert tokens == ["a ", "b"]
