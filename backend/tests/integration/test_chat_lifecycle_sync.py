from __future__ import annotations

import pytest

import app.services.chat_runs as chat_runs


@pytest.mark.anyio
async def test_chat_lifecycle_sync_persists_messages_and_tool_evidence(
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
        answer = f"answer for {conversation_id}: {question}"
        yield {"type": "context_metrics", "used_tokens": 10}
        yield {"type": "token", "token": answer}
        yield {
            "type": "run_map",
            "answer": answer,
            "run_map": {
                "agent": {
                    "agent_name": "netai",
                    "status": "completed",
                    "duration_ms": 110,
                },
                "tool_calls": [
                    {
                        "tool_name": "zabbix_diagnose_host",
                        "input_params": {"host": "edge-01"},
                        "output": {"status": "up"},
                        "status": "success",
                        "error_type": None,
                        "error_message": None,
                        "latency_ms": 64,
                    }
                ],
            },
            "prompt_snapshot": {
                "messages": [
                    {
                        "index": 0,
                        "role": "system",
                        "source": "agent_system_prompt",
                        "text": "NetAI system\n\nTool group guidance [zabbix]",
                        "estimated_tokens": 10,
                    },
                    {
                        "index": 1,
                        "role": "user",
                        "source": "runtime_user",
                        "text": question,
                        "estimated_tokens": 4,
                    },
                    {
                        "index": 2,
                        "role": "assistant",
                        "source": "assistant_response",
                        "text": answer,
                        "estimated_tokens": 8,
                    },
                ],
                "metrics": {"used_tokens": 10},
            },
        }

    monkeypatch.setattr(chat_runs, "run_agent_stream", _fake_run_agent_stream)

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
    assert run["agent_name"] == "netai"
    assert run["sub_agent_calls"] == []
    assert run["child_runs"] == []
    assert len(run["tool_calls"]) == 1
    assert run["tool_calls"][0]["tool_name"] == "zabbix_diagnose_host"
    assert run["tool_calls"][0]["output"] == {"status": "up"}

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    assert convo_resp.status_code == 200
    convo_payload = convo_resp.json()
    assert convo_payload["id"] == conversation_id
    assert len(convo_payload["messages"]) == 2
    user_message = next(
        message for message in convo_payload["messages"] if message["role"] == "user"
    )
    preview_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/prompt-preview",
        json={
            "content": user_message["content"],
            "include_draft": False,
            "user_message_id": user_message["id"],
        },
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert "Tool group guidance [zabbix]" in preview["messages"][0]["text"]
    assert preview["messages"][-1]["source"] == "assistant_response"
    assert "answer for" in preview["messages"][-1]["text"]


@pytest.mark.anyio
async def test_chat_skill_commands_only_apply_explicitly_selected_skills(
    async_client, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    async def _fake_run_agent_stream(
        *,
        conversation_id: str,
        question: str,
        skills: list[dict[str, str]] | None = None,
        **_kwargs: object,
    ):
        captured["conversation_id"] = conversation_id
        captured["question"] = question
        captured["skills"] = skills
        yield {"type": "context_metrics", "used_tokens": 3}
        yield {"type": "token", "token": "ok"}
        yield {
            "type": "run_map",
            "answer": "ok",
            "run_map": {
                "agent": {
                    "agent_name": "netai",
                    "status": "completed",
                    "duration_ms": 1,
                },
                "tool_calls": [],
            },
        }

    monkeypatch.setattr(chat_runs, "run_agent_stream", _fake_run_agent_stream)

    skill_resp = await async_client.post(
        "/api/v1/skills",
        json={
            "name": "WAN Flap Triage",
            "description": "test",
            "instructions": "Investigate WAN instability.",
            "enabled": True,
        },
    )
    assert skill_resp.status_code == 201
    assert skill_resp.json()["slug"] == "wan-flap-triage"

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Ops"}
    )
    conversation_id = create_resp.json()["id"]

    ask_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "/wan-flap-triage investigate edge-01"},
    )
    assert ask_resp.status_code == 200
    assert captured["question"] == "investigate edge-01"
    assert captured["skills"] == [
        {"name": "WAN Flap Triage", "instructions": "Investigate WAN instability."}
    ]

    ask_without_skill_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "investigate edge-02"},
    )
    assert ask_without_skill_resp.status_code == 200
    assert captured["question"] == "investigate edge-02"
    assert captured["skills"] is None

    ask_with_path_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "check /var/log/syslog for edge-03"},
    )
    assert ask_with_path_resp.status_code == 200
    assert captured["question"] == "check /var/log/syslog for edge-03"
    assert captured["skills"] is None

    ask_with_unknown_prefix_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "/var/log edge-04 is flapping"},
    )
    assert ask_with_unknown_prefix_resp.status_code == 200
    assert captured["question"] == "/var/log edge-04 is flapping"
    assert captured["skills"] is None
