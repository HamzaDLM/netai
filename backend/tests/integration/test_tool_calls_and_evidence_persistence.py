from __future__ import annotations

import pytest

import app.api.endpoints.chat as chat_endpoints


@pytest.mark.anyio
async def test_stream_specialist_tool_calls_are_persisted(
    async_client, monkeypatch
) -> None:
    async def _fake_run_agent_stream(*, conversation_id: str, question: str):
        yield {"type": "token", "token": "OK"}
        yield {
            "type": "specialist_tool_call",
            "specialist": "syslog",
            "tool_name": "syslog_specialist",
            "arguments": {"question": "check logs"},
            "evidence": [
                {
                    "type": "syslog",
                    "ref": "evt-1",
                    "content": "interface flaps observed",
                    "score": 0.88,
                }
            ],
        }
        yield {
            "type": "specialist_tool_result",
            "specialist": "syslog",
            "tool_name": "syslog_specialist",
            "result": {"summary": "flaps found"},
        }

    async def _no_title(
        *, conversation_id: str, user_question: str, assistant_content: str
    ) -> None:
        return None

    monkeypatch.setattr(chat_endpoints, "run_agent_stream", _fake_run_agent_stream)
    monkeypatch.setattr(chat_endpoints, "_generate_title_if_missing", _no_title)

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Evidence"}
    )
    conversation_id = create_resp.json()["id"]

    async with async_client.stream(
        "POST",
        f"/api/v1/llm/conversation/{conversation_id}/message/stream",
        json={"content": "find syslog issues"},
    ) as response:
        assert response.status_code == 200
        async for _ in response.aiter_text():
            pass

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    payload = convo_resp.json()
    assistant = [m for m in payload["messages"] if m["role"] == "assistant"][0]

    assert len(assistant["agent_runs"]) == 1
    run = assistant["agent_runs"][0]
    assert run["status"] == "completed"
    events = run["events"]
    assert len(events) == 2
    assert events[0]["event_type"] == "specialist_tool_call"
    assert events[1]["event_type"] == "specialist_tool_result"
    assert events[1]["payload"]["result"] == {"summary": "flaps found"}
    assert "flaps" in events[0]["payload"]["evidence"][0]["content"]
