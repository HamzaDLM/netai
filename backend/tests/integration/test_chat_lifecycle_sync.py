from __future__ import annotations

import pytest

import app.api.endpoints.chat as chat_endpoints


@pytest.mark.anyio
async def test_chat_lifecycle_sync_persists_messages_and_tool_evidence(
    async_client, monkeypatch
) -> None:
    async def _fake_run_agent(*, conversation_id: str, question: str) -> dict:
        return {
            "answer": f"answer for {conversation_id}: {question}",
            "events": [
                {
                    "type": "specialist_tool_call",
                    "specialist": "zabbix",
                    "tool_name": "zabbix.get_host_status",
                    "arguments": {"host": "edge-01"},
                    "evidence": [
                        {
                            "type": "zabbix",
                            "ref": "edge-01",
                            "content": "host edge-01 is up",
                            "score": 0.95,
                        }
                    ],
                },
                {
                    "type": "specialist_tool_result",
                    "specialist": "zabbix",
                    "tool_name": "zabbix.get_host_status",
                    "result": {"status": "up"},
                },
            ],
            "context_metrics": {"used_tokens": 10},
        }

    async def _no_title(
        *, conversation_id: str, user_question: str, assistant_content: str
    ) -> None:
        return None

    monkeypatch.setattr(chat_endpoints, "run_agent", _fake_run_agent)
    monkeypatch.setattr(chat_endpoints, "_generate_title_if_missing", _no_title)

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Ops"}
    )
    assert create_resp.status_code == 200
    conversation = create_resp.json()
    conversation_id = conversation["id"]
    assert isinstance(conversation_id, str)

    ask_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "is edge-01 up?"},
    )
    assert ask_resp.status_code == 200
    ask_payload = ask_resp.json()
    assert "answer for" in ask_payload["content"]
    assert len(ask_payload["agent_runs"]) == 1
    run = ask_payload["agent_runs"][0]
    assert run["status"] == "completed"
    assert len(run["events"]) == 2
    assert run["events"][0]["event_type"] == "specialist_tool_call"
    assert run["events"][1]["event_type"] == "specialist_tool_result"

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    assert convo_resp.status_code == 200
    convo_payload = convo_resp.json()
    assert convo_payload["id"] == conversation_id
    assert len(convo_payload["messages"]) == 2
