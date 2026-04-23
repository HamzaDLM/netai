from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.models.chat import (
    AgentRunStatus,
    AgentType,
    FeedbackRating,
    FeedbackType,
    MessageRole,
    ToolCallStatus,
)


class ORMBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    content: str


class FeedbackCreate(BaseModel):
    rating: FeedbackRating
    feedback_type: FeedbackType | None = None
    feedback_types: list[FeedbackType] | None = None
    comment: str | None = None


class FeedbackResponse(ORMBaseModel):
    id: int
    rating: FeedbackRating
    feedback_type: FeedbackType | None
    comment: str | None
    created_at: datetime
    updated_at: datetime


class ToolCallResponse(ORMBaseModel):
    id: int
    run_id: int
    conversation_id: str
    tool_name: str
    input_params: dict
    output: dict | None
    status: ToolCallStatus
    error_type: str | None
    error_message: str | None
    created_at: datetime


class SubAgentCallResponse(ORMBaseModel):
    id: int
    parent_run_id: int
    child_run_id: int | None
    specialist_name: str
    call_sequence: int
    task_prompt: str
    result_summary: str | None
    status: ToolCallStatus
    created_at: datetime


class SpecialistRunResponse(ORMBaseModel):
    id: int
    conversation_id: str
    user_message_id: int
    assistant_message_id: int | None
    parent_run_id: int | None
    agent_type: AgentType
    agent_name: str
    depth: int
    status: AgentRunStatus
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    final_answer: str | None
    context_metrics: dict | None
    error: str | None
    tool_calls: list[ToolCallResponse] = []
    created_at: datetime
    updated_at: datetime


class AgentRunResponse(ORMBaseModel):
    id: int
    conversation_id: str
    user_message_id: int
    assistant_message_id: int | None
    parent_run_id: int | None
    agent_type: AgentType
    agent_name: str
    depth: int
    status: AgentRunStatus
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    final_answer: str | None
    context_metrics: dict | None
    error: str | None
    sub_agent_calls: list[SubAgentCallResponse] = []
    child_runs: list[SpecialistRunResponse] = []
    tool_calls: list[ToolCallResponse] = []
    created_at: datetime
    updated_at: datetime


class MessageResponse(ORMBaseModel):
    id: int
    role: MessageRole
    content: str
    agent_runs: list[AgentRunResponse] = []
    feedback: list[FeedbackResponse] = []
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    title: str


class ConversationResponse(ORMBaseModel):
    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationMessagesResponse(ConversationResponse):
    messages: list[MessageResponse]
