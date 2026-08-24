import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class EvalEvaluatorKind(str, enum.Enum):
    deterministic = "deterministic"
    llm_judge = "llm_judge"


class EvalEvaluatorRule(str, enum.Enum):
    tool_trajectory = "tool_trajectory"
    completion_safety = "completion_safety"
    llm_judge = "llm_judge"


class EvalRunStatus(str, enum.Enum):
    running = "running"
    passed = "passed"
    failed = "failed"


class EvalEvaluator(Base):
    __table_args__ = (
        Index("ix_eval_evaluator_archived_created", "archived", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[EvalEvaluatorKind] = mapped_column(
        Enum(EvalEvaluatorKind), nullable=False
    )
    rule: Mapped[EvalEvaluatorRule] = mapped_column(
        Enum(EvalEvaluatorRule), nullable=False
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    criteria: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=85)
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class EvalScenario(Base):
    __table_args__ = (
        Index("ix_eval_scenario_archived_created", "archived", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False
    )
    owner_name: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    fixture: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    required_tools: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    forbidden_tools: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    expected_facts: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    evaluator_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class EvalRun(Base):
    __table_args__ = (
        Index("ix_eval_run_scenario_created", "scenario_id", "created_at"),
        Index("ix_eval_run_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("eval_scenario.id"), nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id"), nullable=False
    )
    status: Mapped[EvalRunStatus] = mapped_column(Enum(EvalRunStatus), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(120), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    checks: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    error: Mapped[str | None] = mapped_column(Text)
