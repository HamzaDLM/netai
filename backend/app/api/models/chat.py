import enum
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class ToolCallStatus(str, enum.Enum):
    running = "running"
    success = "success"
    error = "error"
    timeout = "timeout"
    blocked = "blocked"  # requires_approval and not yet approved


class AgentType(str, enum.Enum):
    orchestrator = "orchestrator"
    specialist = "specialist"


def _generate_conversation_hash_id() -> str:
    # URL-safe, short, and non-sequential identifier for public/API usage.
    return secrets.token_urlsafe(12)


class Conversation(Base):
    __table_args__ = (
        Index(
            "ix_conversation_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=_generate_conversation_hash_id,
    )

    title: Mapped[str | None] = mapped_column(String(255))
    user_id: Mapped[int] = mapped_column(index=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    summaries: Mapped[list["ConversationSummary"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class ConversationSummary(Base):
    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversation.id"), index=True
    )
    content: Mapped[str] = mapped_column(Text)

    up_to_message_id: Mapped[int] = mapped_column(
        ForeignKey("message.id"), index=True, nullable=False
    )
    conversation: Mapped["Conversation"] = relationship(back_populates="summaries")
    up_to_message: Mapped["Message"] = relationship(foreign_keys=[up_to_message_id])


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class Message(Base):
    __table_args__ = (
        Index("ix_message_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversation.id"), index=True, nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text)
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
    """
    One row per agent invocation:
    orchestrator (depth=0) | specialist (depth=1).
    Parent/child linked via parent_run_id.
    """

    __table_args__ = (
        Index("ix_agent_run_conversation_depth", "conversation_id", "depth"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversation.id"), index=True, nullable=False
    )
    user_message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), index=True)
    assistant_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("message.id"), index=True
    )

    # Hierarchy
    parent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_run.id"), index=True
    )
    agent_type: Mapped[AgentType] = mapped_column(Enum(AgentType), nullable=False)
    agent_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "Zabbix Specialist"
    depth: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # 0=orchestrator, 1=specialist

    # Status & Timing
    status: Mapped[AgentRunStatus] = mapped_column(Enum(AgentRunStatus))
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[int | None]

    # Output
    final_answer: Mapped[str | None] = mapped_column(Text)
    context_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)

    conversation: Mapped["Conversation"] = relationship(back_populates="agent_runs")
    user_message: Mapped["Message|None"] = relationship(foreign_keys=[user_message_id])
    assistant_message: Mapped["Message|None"] = relationship(
        back_populates="agent_runs",
        foreign_keys=[assistant_message_id],
    )
    parent_run: Mapped["AgentRun|None"] = relationship(
        back_populates="child_runs", remote_side="AgentRun.id"
    )
    child_runs: Mapped[list["AgentRun"]] = relationship(back_populates="parent_run")
    sub_agent_calls: Mapped[list["SubAgentCall"]] = relationship(
        back_populates="parent_run",
        foreign_keys="SubAgentCall.parent_run_id",
        order_by="SubAgentCall.call_sequence",
        cascade="all, delete-orphan",
    )
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="run",
        order_by="ToolCall.id",
        cascade="all, delete-orphan",
    )


class SubAgentCall(Base):
    """
    The orchestrator's act of delegating to a specialist.
    Bridges parent AgentRun (orchestrator) → child AgentRun (specialist).
    """

    id: Mapped[int] = mapped_column(primary_key=True)

    parent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_run.id"), index=True, nullable=False
    )
    child_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_run.id"), index=True
    )  # null until specialist starts
    specialist_name: Mapped[str] = mapped_column(String(64), nullable=False)
    call_sequence: Mapped[int] = mapped_column(
        nullable=False
    )  # order within the orchestrator run
    task_prompt: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # what orchestrator asked
    result_summary: Mapped[str | None] = mapped_column(Text)  # what specialist returned
    status: Mapped[ToolCallStatus] = mapped_column(
        Enum(ToolCallStatus), nullable=False, default=ToolCallStatus.running
    )

    parent_run: Mapped["AgentRun"] = relationship(
        back_populates="sub_agent_calls", foreign_keys=[parent_run_id]
    )
    child_run: Mapped["AgentRun|None"] = relationship(foreign_keys=[child_run_id])


class ToolCall(Base):
    """
    A specialist's toolcalling against network infrastructure.
    Only lives on specialist runs (depth=1).
    """

    __table_args__ = (Index("ix_tool_call_run_tool", "run_id", "tool_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_run.id"), index=True, nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), index=True, nullable=False
    )

    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)

    input_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSON)

    status: Mapped[ToolCallStatus] = mapped_column(Enum(ToolCallStatus), nullable=False)
    error_type: Mapped[str | None] = mapped_column(
        String(64)
    )  # "auth_failed", "timeout", "connection_refused"
    error_message: Mapped[str | None] = mapped_column(Text)

    run: Mapped["AgentRun"] = relationship(back_populates="tool_calls")


class FeedbackType(str, enum.Enum):
    wrong_diagnosis = "wrong_diagnosis"
    hallucination = "hallucination"
    correct_but_incomplete = "correct_but_incomplete"
    irrelevant_specialist = "irrelevant_specialist"
    wrong_toolcall_use = "wrong_toolcall_use"
    other = "other"


class FeedbackRating(str, enum.Enum):
    good = "good"
    bad = "bad"


class Feedback(Base):
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("message.id"), index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    rating: Mapped[FeedbackRating] = mapped_column(Enum(FeedbackRating))
    feedback_type: Mapped[FeedbackType | None] = mapped_column(Enum(FeedbackType))
    comment: Mapped[str | None] = mapped_column(Text)
    message: Mapped["Message"] = relationship(back_populates="feedback")
