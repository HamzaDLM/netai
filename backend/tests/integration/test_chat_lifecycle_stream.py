from __future__ import annotations

import pytest

import app.api.endpoints.chat as chat_endpoints


@pytest.mark.anyio
async def test_chat_stream_emits_sse_and_persists_assistant_message(
    async_client, monkeypatch
) -> None:
    async def _fake_run_agent_stream(*, conversation_id: str, question: str):
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
