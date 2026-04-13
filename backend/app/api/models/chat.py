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
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="assistant_message",
        foreign_keys="AgentRun.assistant_message_id",
        cascade="all, delete-orphan",
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class AgentRunStatus(str, enum.Enum):
    running = "running"
    completed = "completed"
    failed = "failed"


class AgentRun(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversation.id"), index=True
    )
    user_message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), index=True)
    assistant_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("message.id"), index=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(Enum(AgentRunStatus))
    final_answer: Mapped[str | None] = mapped_column(Text)
    context_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    ended_at: Mapped[datetime | None]
    conversation: Mapped["Conversation"] = relationship()
    assistant_message: Mapped["Message"] = relationship(
        back_populates="agent_runs",
        foreign_keys=[assistant_message_id],
    )
    events: Mapped[list["AgentEvent"]] = relationship(
        back_populates="run",
        order_by="AgentEvent.event_sequence",
        cascade="all, delete-orphan",
    )


class AgentEvent(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_run.id"), index=True)
    event_sequence: Mapped[int] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    actor_type: Mapped[str | None] = mapped_column(String(32))
    actor_name: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    run: Mapped["AgentRun"] = relationship(back_populates="events")


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
