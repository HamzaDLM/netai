import enum
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Enum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


def _generate_conversation_hash_id() -> str:
    # URL-safe, short, and non-sequential identifier for public/API usage.
    return secrets.token_urlsafe(12)


class Conversation(Base):
    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=_generate_conversation_hash_id,
    )
    title: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[int] = mapped_column(index=True)
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    summaries: Mapped[list["ConversationSummary"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(Base):
    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversation.id"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole))
    content: Mapped[str] = mapped_column(Text)
    question: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))
    token_input: Mapped[int | None]
    token_output: Mapped[int | None]
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class ToolCallStatus(str, enum.Enum):
    success = "success"
    error = "error"


class ToolCall(Base):
    id: Mapped[int] = mapped_column(primary_key=True)

    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    tool_source: Mapped[str | None] = mapped_column(String(50))
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    latency_ms: Mapped[int | None]
    status: Mapped[ToolCallStatus | None] = mapped_column(Enum(ToolCallStatus))
    message: Mapped["Message"] = relationship(back_populates="tool_calls")
    evidence_items: Mapped[list["Evidence"]] = relationship(
        back_populates="tool_call",
        cascade="all, delete-orphan",
    )


class Evidence(Base):
    id: Mapped[int] = mapped_column(primary_key=True)

    tool_call_id: Mapped[int] = mapped_column(ForeignKey("toolcall.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(50))
    source_ref: Mapped[str | None] = mapped_column(String(255))
    content_snippet: Mapped[str] = mapped_column(Text)
    score: Mapped[float | None]
    timestamp: Mapped[datetime | None]
    tool_call: Mapped["ToolCall"] = relationship(back_populates="evidence_items")


class FeedbackRating(str, enum.Enum):
    good = "good"
    bad = "bad"


class Feedback(Base):
    id: Mapped[int] = mapped_column(primary_key=True)

    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    rating: Mapped[FeedbackRating] = mapped_column(Enum(FeedbackRating))
    comment: Mapped[str | None] = mapped_column(Text)
    message: Mapped["Message"] = relationship(back_populates="feedback")


class ConversationSummary(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversation.id"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    up_to_message_id: Mapped[int] = mapped_column(index=True)
    conversation: Mapped["Conversation"] = relationship(back_populates="summaries")
