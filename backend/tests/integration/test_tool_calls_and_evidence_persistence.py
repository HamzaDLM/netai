from __future__ import annotations

import pytest

import app.api.endpoints.chat as chat_endpoints


@pytest.mark.anyio
async def test_stream_specialist_tool_calls_are_persisted(
    async_client, monkeypatch
) -> None:
    async def _fake_run_agent_stream(
        *,
        conversation_id: str,
        question: str,
        skills: list[dict[str, str]] | None = None,
    ):
        _ = skills
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
            "type": "specialist_evidence",
            "specialist": "syslog",
            "tool_name": "syslog_specialist",
            "result": {"summary": "flaps found"},
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
            "type": "run_map",
            "answer": "OK",
            "run_map": {
                "orchestrator": {
                    "agent_name": "orchestrator",
                    "status": "completed",
                    "duration_ms": 50,
                    "specialists": ["syslog"],
                    "reasoning": "syslog selected",
                },
                "sub_agent_calls": [
                    {
                        "specialist_name": "syslog",
                        "call_sequence": 1,
                        "task_prompt": "find syslog issues",
                        "plan": "query log evidence",
                        "result_summary": "flaps found",
                        "status": "success",
                        "duration_ms": 30,
                        "tool_calls": [
                            {
                                "tool_name": "syslog_search",
                                "input_params": {"target": "core-sw-01"},
                                "output": {"summary": "flaps found"},
                                "status": "success",
                                "error_type": None,
                                "error_message": None,
                                "latency_ms": 30,
                                "evidence": [
                                    {
                                        "type": "syslog",
                                        "ref": "evt-1",
                                        "content": "interface flaps observed",
                                        "score": 0.88,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
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
    assert len(run["sub_agent_calls"]) == 1
    assert run["sub_agent_calls"][0]["specialist_name"] == "syslog"
    assert len(run["child_runs"]) == 1
    specialist_run = run["child_runs"][0]
    assert specialist_run["agent_name"] == "syslog"
    assert len(specialist_run["tool_calls"]) == 1
    tool_call = specialist_run["tool_calls"][0]
    assert tool_call["tool_name"] == "syslog_search"
    assert tool_call["output"]["summary"] == "flaps found"
    assert "flaps" in tool_call["output"]["evidence"][0]["content"]
