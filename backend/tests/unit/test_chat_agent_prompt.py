from haystack.dataclasses import ChatMessage

from app.services.chat_agent import _replace_latest_user


def test_replacing_persisted_question_removes_later_answer() -> None:
    messages = [
        ChatMessage.from_user("first question"),
        ChatMessage.from_assistant("first answer"),
        ChatMessage.from_user("latest question"),
        ChatMessage.from_assistant("latest answer"),
    ]
    sources: list[dict[str, int | str | None]] = [
        {"source": "conversation_message", "message_id": index} for index in range(1, 5)
    ]

    _replace_latest_user(messages, sources, "latest question")

    assert [message.text for message in messages] == [
        "first question",
        "first answer",
        "latest question",
    ]
    assert [source["message_id"] for source in sources] == [1, 2, 3]
