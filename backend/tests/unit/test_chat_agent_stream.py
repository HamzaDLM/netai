from __future__ import annotations

from types import SimpleNamespace

import pytest
from haystack.dataclasses import ChatMessage

from app.services import chat_agent
from app.services.netai import NetAIRun


class IntroThenFinalService:
    async def run(self, *, observer, **_kwargs: object) -> NetAIRun:
        await observer.emit("token", {"token": "I will inspect the topology."})
        return NetAIRun(
            answer="The topology investigation is complete.",
            duration_ms=5,
            result={},
            observer=observer,
        )


@pytest.mark.anyio
async def test_stream_appends_final_answer_after_pre_tool_text(monkeypatch) -> None:
    async def fake_prepare_agent_prompt(**_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(
            messages=[ChatMessage.from_user("Inspect topology")],
            metrics={},
        )

    monkeypatch.setattr(
        chat_agent,
        "prepare_agent_prompt",
        fake_prepare_agent_prompt,
    )

    events = [
        event
        async for event in chat_agent.run_agent_stream(
            service=IntroThenFinalService(),  # type: ignore[arg-type]
            conversation_id="conversation-stream-finalization",
            question="Inspect topology",
            user_id=7,
        )
    ]

    rendered_text = "".join(
        str(event.get("token") or "")
        for event in events
        if event.get("type") == "token"
    )
    assert rendered_text == (
        "I will inspect the topology.\n\nThe topology investigation is complete."
    )
    run_map_event = next(event for event in events if event.get("type") == "run_map")
    assert run_map_event["answer"] == "The topology investigation is complete."
