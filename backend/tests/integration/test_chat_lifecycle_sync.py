from __future__ import annotations

import pytest

import app.api.endpoints.chat as chat_endpoints


@pytest.mark.anyio
async def test_chat_lifecycle_sync_persists_messages_and_tool_evidence(
    async_client, monkeypatch
) -> None:
    async def _fake_run_agent(
        *,
        conversation_id: str,
        question: str,
        skills: list[dict[str, str]] | None = None,
    ) -> dict:
        _ = skills
        return {
            "answer": f"answer for {conversation_id}: {question}",
            "events": [],
            "run_map": {
                "orchestrator": {
                    "agent_name": "orchestrator",
                    "status": "completed",
                    "duration_ms": 110,
                    "specialists": ["zabbix"],
                    "reasoning": "zabbix selected for monitoring data",
                },
                "sub_agent_calls": [
                    {
                        "specialist_name": "zabbix",
                        "call_sequence": 1,
                        "task_prompt": "is edge-01 up?",
                        "plan": "check host health",
                        "result_summary": "host is up",
                        "status": "success",
                        "duration_ms": 64,
                        "error_message": None,
                        "tool_calls": [
                            {
                                "tool_name": "zabbix_diagnose_host",
                                "input_params": {"host": "edge-01"},
                                "output": {"status": "up"},
                                "status": "success",
                                "error_type": None,
                                "error_message": None,
                                "latency_ms": 64,
                                "evidence": [
                                    {
                                        "type": "zabbix",
                                        "ref": "edge-01",
                                        "content": "host edge-01 is up",
                                        "score": 0.95,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
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
    assert run["agent_type"] == "orchestrator"
    assert len(run["sub_agent_calls"]) == 1
    assert run["sub_agent_calls"][0]["specialist_name"] == "zabbix"
    assert len(run["child_runs"]) == 1
    child = run["child_runs"][0]
    assert child["agent_type"] == "specialist"
    assert child["agent_name"] == "zabbix"
    assert len(child["tool_calls"]) == 1
    assert child["tool_calls"][0]["tool_name"] == "zabbix_diagnose_host"
    assert child["tool_calls"][0]["output"]["evidence"][0]["content"] == (
        "host edge-01 is up"
    )

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    assert convo_resp.status_code == 200
    convo_payload = convo_resp.json()
    assert convo_payload["id"] == conversation_id
    assert len(convo_payload["messages"]) == 2
