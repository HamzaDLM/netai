from __future__ import annotations

import pytest

import app.api.endpoints.chat as chat_endpoints
import app.services.chat_runs as chat_runs
from app.services.chat_agent import AgentPromptSnapshot, PromptSnapshotMessage


@pytest.mark.anyio
async def test_chat_stream_emits_sse_and_persists_assistant_message(
    async_client, monkeypatch
) -> None:
    async def _fake_run_agent_stream(
        *,
        conversation_id: str,
        question: str,
        skills: list[dict[str, str]] | None = None,
        **_kwargs: object,
    ):
        _ = skills
        yield {"type": "context_metrics", "used_tokens": 11, "used_percent": 1}
        yield {"type": "token", "token": "Hel"}
        yield {
            "type": "tool_started",
            "event_sequence": 3,
            "event_id": "evt-tool-started",
            "tool_call_id": "tool-ping",
            "tool_name": "network_ping",
            "arguments": {"target": "edge.example.net"},
        }
        yield {
            "type": "artifact_snapshot",
            "event_sequence": 4,
            "event_id": "evt-artifact-snapshot",
            "artifact": {
                "id": "artifact-ping",
                "kind": "network.ping.v1",
                "schema_version": 1,
                "status": "running",
                "title": "Ping edge.example.net",
                "data": {
                    "target": "edge.example.net",
                    "simulated": True,
                    "count": 1,
                    "sent": 0,
                    "received": 0,
                    "loss_percent": 0,
                    "samples": [],
                },
                "provenance": {"simulated": True},
            },
        }
        yield {
            "type": "artifact_delta",
            "event_sequence": 5,
            "event_id": "evt-artifact-delta",
            "artifact_id": "artifact-ping",
            "status": "completed",
            "set": {"sent": 1, "received": 1},
            "append": {
                "samples": [
                    {
                        "sequence": 1,
                        "status": "reply",
                        "latency_ms": 12.5,
                    }
                ]
            },
        }
        yield {
            "type": "tool_completed",
            "event_sequence": 6,
            "event_id": "evt-tool-completed",
            "tool_call_id": "tool-ping",
            "tool_name": "network_ping",
            "duration_ms": 50,
        }
        yield {"type": "token", "token": "lo"}
        yield {
            "type": "run_map",
            "answer": "Hello",
            "run_map": {
                "agent": {
                    "agent_name": "netai",
                    "status": "completed",
                    "duration_ms": 50,
                },
                "tool_calls": [],
            },
        }

    monkeypatch.setattr(chat_runs, "run_agent_stream", _fake_run_agent_stream)

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Streaming"}
    )
    conversation_id = create_resp.json()["id"]

    async with async_client.stream(
        "POST",
        f"/api/v1/llm/conversation/{conversation_id}/message/stream",
        json={"content": "hello"},
    ) as response:
        assert response.status_code == 200
        body = ""
        async for chunk in response.aiter_text():
            body += chunk

    assert "event: run_accepted" in body
    assert "event: assistant_token" in body
    assert "event: artifact_snapshot" in body
    assert "event: artifact_delta" in body
    assert "event: done" in body

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    payload = convo_resp.json()
    assistant_messages = [m for m in payload["messages"] if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0]["content"] == "Hello"
    run_events = assistant_messages[0]["agent_runs"][0]["events"]
    assert [event["event_type"] for event in run_events] == [
        "tool_started",
        "artifact_snapshot",
        "artifact_delta",
        "tool_completed",
    ]
    assert run_events[1]["payload"]["assistant_offset"] == 3
    assert run_events[1]["correlation_id"] == "artifact-ping"


@pytest.mark.anyio
async def test_prompt_preview_returns_prompt_snapshot(
    async_client, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    async def _fake_build_agent_prompt_snapshot(
        *,
        conversation_id: str,
        question: str,
        skills: list[dict[str, str]] | None = None,
        custom_instructions: str | None = None,
        include_draft_question: bool = True,
        **_kwargs: object,
    ):
        _ = conversation_id, skills, custom_instructions
        captured["include_draft_question"] = include_draft_question
        return AgentPromptSnapshot(
            messages=[
                PromptSnapshotMessage(
                    index=0,
                    role="system",
                    source="agent_system_prompt",
                    text="system",
                    estimated_tokens=1,
                ),
                PromptSnapshotMessage(
                    index=1,
                    role="user",
                    source="current_question",
                    text=question,
                    estimated_tokens=1,
                ),
            ],
            metrics={
                "context_window": 100_000,
                "used_tokens": 2,
                "used_percent": 1,
                "left_tokens": 99_998,
                "left_percent": 99,
                "compacted": False,
                "summary_id": None,
            },
        )

    monkeypatch.setattr(
        chat_endpoints,
        "build_agent_prompt_snapshot",
        _fake_build_agent_prompt_snapshot,
    )

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Preview"}
    )
    conversation_id = create_resp.json()["id"]

    response = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/prompt-preview",
        json={"content": "show context", "include_draft": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["used_tokens"] == 2
    assert [message["source"] for message in payload["messages"]] == [
        "agent_system_prompt",
        "current_question",
    ]
    assert payload["messages"][1]["text"] == "show context"
    assert captured["include_draft_question"] is False
