from __future__ import annotations

import pytest

import app.api.endpoints.chat as chat_endpoints
from app.workflows.agent_runner import AgentPromptSnapshot, PromptSnapshotMessage


@pytest.mark.anyio
async def test_chat_stream_emits_sse_and_persists_assistant_message(
    async_client, monkeypatch
) -> None:
    async def _fake_run_agent_stream(
        *,
        conversation_id: str,
        question: str,
        skills: list[dict[str, str]] | None = None,
    ):
        _ = skills
        yield {"type": "context_metrics", "used_tokens": 11, "used_percent": 1}
        yield {"type": "token", "token": "Hel"}
        yield {"type": "token", "token": "lo"}
        yield {"type": "leader_conclusion", "answer": "Hello"}

    async def _no_title(
        *, conversation_id: str, user_question: str, assistant_content: str
    ) -> None:
        return None

    monkeypatch.setattr(chat_endpoints, "run_agent_stream", _fake_run_agent_stream)
    monkeypatch.setattr(chat_endpoints, "_generate_title_if_missing", _no_title)

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

    assert "event: assistant_token" in body
    assert "event: leader_conclusion" in body
    assert "event: done" in body

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    payload = convo_resp.json()
    assistant_messages = [m for m in payload["messages"] if m["role"] == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0]["content"] == "Hello"


@pytest.mark.anyio
async def test_prompt_preview_returns_prompt_snapshot(
    async_client, monkeypatch
) -> None:
    async def _fake_build_agent_prompt_snapshot(
        *,
        conversation_id: str,
        question: str,
        skills: list[dict[str, str]] | None = None,
        custom_instructions: str | None = None,
    ):
        _ = conversation_id, skills, custom_instructions
        return AgentPromptSnapshot(
            messages=[
                PromptSnapshotMessage(
                    index=0,
                    role="system",
                    source="orchestrator_system_prompt",
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
        json={"content": "show context"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["used_tokens"] == 2
    assert [message["source"] for message in payload["messages"]] == [
        "orchestrator_system_prompt",
        "current_question",
    ]
    assert payload["messages"][1]["text"] == "show context"
