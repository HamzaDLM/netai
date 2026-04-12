from types import SimpleNamespace
from typing import cast

from haystack.dataclasses import ChatMessage

from app.api.models.chat import Message, MessageRole
from app.workflows import context_manager


def test_estimate_tokens_uses_coarse_character_heuristic() -> None:
    messages = [ChatMessage.from_user("abcd"), ChatMessage.from_user("efgh")]
    assert context_manager._estimate_tokens(messages) == 2


def test_estimate_tokens_never_returns_zero() -> None:
    assert context_manager._estimate_tokens([]) == 1


def test_format_messages_for_summary_skips_system_messages() -> None:
    messages = cast(
        list[Message],
        [
            SimpleNamespace(id=1, role=MessageRole.system, content="sys"),
            SimpleNamespace(id=2, role=MessageRole.user, content="hello"),
            SimpleNamespace(id=3, role=MessageRole.assistant, content="world"),
        ],
    )

    rendered = context_manager._format_messages_for_summary(messages)

    assert "[1]" not in rendered
    assert "[2] user: hello" in rendered
    assert "[3] assistant: world" in rendered
