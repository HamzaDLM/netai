from __future__ import annotations

import pytest

import app.services.chat_runs as chat_runs


@pytest.mark.anyio
async def test_stream_agent_tool_calls_are_persisted(async_client, monkeypatch) -> None:
    async def fake_stream(**_kwargs: object):
        yield {"type": "token", "token": "OK"}
        yield {
            "type": "run_map",
            "answer": "OK",
            "run_map": {
                "agent": {
                    "agent_name": "netai",
                    "status": "completed",
                    "duration_ms": 50,
                },
                "tool_calls": [
                    {
                        "tool_name": "syslog_get_device_events",
                        "input_params": {"hostname": "core-sw-01"},
                        "output": {
                            "count": 1,
                            "events": [{"message": "interface flaps observed"}],
                        },
                        "status": "success",
                        "error_type": None,
                        "error_message": None,
                        "latency_ms": 30,
                    }
                ],
            },
        }

    monkeypatch.setattr(chat_runs, "run_agent_stream", fake_stream)

    create_response = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Evidence"}
    )
    conversation_id = create_response.json()["id"]

    async with async_client.stream(
        "POST",
        f"/api/v1/llm/conversation/{conversation_id}/message/stream",
        json={"content": "find syslog issues"},
    ) as response:
        assert response.status_code == 200
        stream_text = "".join([chunk async for chunk in response.aiter_text()])

    assert '"duration_ms": 50' in stream_text

    conversation_response = await async_client.get(
        f"/api/v1/llm/conversation/{conversation_id}"
    )
    assistant = next(
        message
        for message in conversation_response.json()["messages"]
        if message["role"] == "assistant"
    )
    run = assistant["agent_runs"][0]
    assert run["agent_name"] == "netai"
    assert run["sub_agent_calls"] == []
    assert run["child_runs"] == []
    assert len(run["tool_calls"]) == 1
    tool_call = run["tool_calls"][0]
    assert tool_call["tool_name"] == "syslog_get_device_events"
    assert tool_call["output"]["count"] == 1
    assert "flaps" in tool_call["output"]["events"][0]["message"]
