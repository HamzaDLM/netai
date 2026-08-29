from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import app.services.chat_runs as chat_runs
from app.api.models.chat import AgentRun, AgentRunStatus, Conversation, Message
from app.services.chat_runs import (
    FAILED_RESPONSE,
    ActiveConversationRunError,
    ChatRunCoordinator,
    ChatRunRequest,
)


async def _conversation(session_factory, *, title: str = "Durable run") -> str:
    async with session_factory() as db:
        conversation = Conversation(title=title, user_id=0)
        db.add(conversation)
        await db.commit()
        return conversation.id


def _request(conversation_id: str, *, question: str = "inspect edge-01"):
    return ChatRunRequest(
        conversation_id=conversation_id,
        raw_question=question,
        agent_question=question,
        user_id=0,
        request_id="request-test",
    )


def _service():
    return SimpleNamespace(settings=SimpleNamespace(AGENT_RUN_TIMEOUT_SECONDS=300.0))


@pytest.mark.anyio
async def test_disconnecting_stream_does_not_cancel_agent_run(
    test_db_session_factory,
    monkeypatch,
) -> None:
    conversation_id = await _conversation(test_db_session_factory)
    release = asyncio.Event()
    started_execution = asyncio.Event()

    async def delayed_stream(**_kwargs: object):
        started_execution.set()
        yield {"type": "token", "token": "Investigation "}
        await release.wait()
        yield {"type": "token", "token": "complete."}
        yield {
            "type": "run_map",
            "answer": "Investigation complete.",
            "run_map": {"agent": {"duration_ms": 20}, "tool_calls": []},
        }

    monkeypatch.setattr(chat_runs, "run_agent_stream", delayed_stream)
    coordinator: ChatRunCoordinator = ChatRunCoordinator(
        service=_service(),  # type: ignore[arg-type]
        session_factory=test_db_session_factory,
    )
    started = await coordinator.start(_request(conversation_id))
    await started_execution.wait()
    event_iterator = started.subscription.events()
    assert (await anext(event_iterator))["type"] == "assistant_token"
    await event_iterator.aclose()

    release.set()
    await started.task

    async with test_db_session_factory() as db:
        assistant = await db.get(Message, started.assistant_message_id)
        run = await db.get(AgentRun, started.run_id)
    assert assistant is not None
    assert assistant.content == "Investigation complete."
    assert run is not None
    assert run.status == AgentRunStatus.completed


@pytest.mark.anyio
async def test_failed_run_is_persisted_and_visible_to_the_user(
    test_db_session_factory,
    monkeypatch,
) -> None:
    conversation_id = await _conversation(test_db_session_factory)

    async def failing_stream(**_kwargs: object):
        yield {"type": "context_metrics", "used_tokens": 4}
        raise RuntimeError("provider failed")

    monkeypatch.setattr(chat_runs, "run_agent_stream", failing_stream)
    coordinator: ChatRunCoordinator = ChatRunCoordinator(
        service=_service(),  # type: ignore[arg-type]
        session_factory=test_db_session_factory,
    )
    started = await coordinator.start(_request(conversation_id))
    await started.task

    async with test_db_session_factory() as db:
        assistant = await db.get(Message, started.assistant_message_id)
        run = await db.get(AgentRun, started.run_id)
    assert assistant is not None
    assert assistant.content == FAILED_RESPONSE
    assert run is not None
    assert run.status == AgentRunStatus.failed
    assert run.error == "RuntimeError: provider failed"


@pytest.mark.anyio
async def test_conversation_rejects_a_second_active_run(
    test_db_session_factory,
    monkeypatch,
) -> None:
    conversation_id = await _conversation(test_db_session_factory)
    release = asyncio.Event()
    started_execution = asyncio.Event()

    async def blocked_stream(**_kwargs: object):
        started_execution.set()
        await release.wait()
        yield {"type": "token", "token": "done"}

    monkeypatch.setattr(chat_runs, "run_agent_stream", blocked_stream)
    coordinator: ChatRunCoordinator = ChatRunCoordinator(
        service=_service(),  # type: ignore[arg-type]
        session_factory=test_db_session_factory,
    )
    first = await coordinator.start(_request(conversation_id))
    await started_execution.wait()

    with pytest.raises(ActiveConversationRunError, match="active run"):
        await coordinator.start(_request(conversation_id, question="second"))

    release.set()
    await first.task
