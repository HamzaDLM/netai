from __future__ import annotations

import pytest
from sqlalchemy import select

import app.api.endpoints.chat as chat_endpoints
from app.api.models.chat import Feedback


async def _fake_run_agent(*, conversation_id: str, question: str, skills=None) -> dict:
    return {
        "answer": f"answer for {conversation_id}: {question}",
        "events": [],
        "run_map": {},
        "context_metrics": {"used_tokens": 5},
    }


async def _no_title(
    *, conversation_id: str, user_question: str, assistant_content: str
) -> None:
    return None


@pytest.mark.anyio
async def test_submit_feedback_persists_row(
    async_client, test_db_session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(chat_endpoints, "run_agent", _fake_run_agent)
    monkeypatch.setattr(chat_endpoints, "_generate_title_if_missing", _no_title)

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Feedback test"}
    )
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["id"]

    ask_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "hello"},
    )
    assert ask_resp.status_code == 200
    assistant_message_id = ask_resp.json()["id"]

    feedback_resp = await async_client.post(
        f"/api/v1/llm/messages/{assistant_message_id}/feedback",
        json={
            "rating": "bad",
            "feedback_type": "wrong_toolcall_use",
            "comment": "picked the wrong tool",
        },
    )
    assert feedback_resp.status_code == 200

    second_feedback_resp = await async_client.post(
        f"/api/v1/llm/messages/{assistant_message_id}/feedback",
        json={"rating": "good"},
    )
    assert second_feedback_resp.status_code == 200

    async with test_db_session_factory() as session:
        result = await session.execute(select(Feedback))
        rows = result.scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.message_id == assistant_message_id
        assert row.user_id == 0
        assert row.rating.value == "good"
        assert row.feedback_type is None
        assert row.comment is None

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    assert convo_resp.status_code == 200
    messages = convo_resp.json()["messages"]
    assistant_message = next(
        (item for item in messages if item["id"] == assistant_message_id), None
    )
    assert assistant_message is not None
    assert len(assistant_message["feedback"]) == 1
    assert assistant_message["feedback"][0]["rating"] == "good"


@pytest.mark.anyio
async def test_submit_feedback_rejects_user_message(async_client, monkeypatch) -> None:
    monkeypatch.setattr(chat_endpoints, "run_agent", _fake_run_agent)
    monkeypatch.setattr(chat_endpoints, "_generate_title_if_missing", _no_title)

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Feedback test"}
    )
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["id"]

    ask_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "hello"},
    )
    assert ask_resp.status_code == 200

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    assert convo_resp.status_code == 200
    user_message_id = convo_resp.json()["messages"][0]["id"]

    feedback_resp = await async_client.post(
        f"/api/v1/llm/messages/{user_message_id}/feedback",
        json={"rating": "good"},
    )
    assert feedback_resp.status_code == 400
    assert (
        feedback_resp.json()["detail"]
        == "feedback_only_supported_for_assistant_messages"
    )


@pytest.mark.anyio
async def test_submit_feedback_accepts_multiple_feedback_types(
    async_client, test_db_session_factory, monkeypatch
) -> None:
    monkeypatch.setattr(chat_endpoints, "run_agent", _fake_run_agent)
    monkeypatch.setattr(chat_endpoints, "_generate_title_if_missing", _no_title)

    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Feedback multi-type test"}
    )
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["id"]

    ask_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "hello"},
    )
    assert ask_resp.status_code == 200
    assistant_message_id = ask_resp.json()["id"]

    feedback_resp = await async_client.post(
        f"/api/v1/llm/messages/{assistant_message_id}/feedback",
        json={
            "rating": "bad",
            "feedback_types": ["wrong_diagnosis", "irrelevant_specialist"],
            "comment": "both routing and answer quality issues",
        },
    )
    assert feedback_resp.status_code == 200

    async with test_db_session_factory() as session:
        result = await session.execute(select(Feedback).order_by(Feedback.id.asc()))
        rows = result.scalars().all()
        assert len(rows) == 2
        assert {row.feedback_type.value for row in rows if row.feedback_type} == {
            "wrong_diagnosis",
            "irrelevant_specialist",
        }
        assert all(row.rating.value == "bad" for row in rows)
        assert all(
            row.comment == "both routing and answer quality issues" for row in rows
        )

    convo_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    assert convo_resp.status_code == 200
    messages = convo_resp.json()["messages"]
    assistant_message = next(
        (item for item in messages if item["id"] == assistant_message_id), None
    )
    assert assistant_message is not None
    assert len(assistant_message["feedback"]) == 2
