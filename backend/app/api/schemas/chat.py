from datetime import datetime

from pydantic import BaseModel

from app.api.models.chat import AgentRunStatus, MessageRole


class MessageCreate(BaseModel):
    content: str


class FeedbackCreate(BaseModel):
    rating: str
    comment: str | None = None


class AgentEventResponse(BaseModel):
    id: int
    event_sequence: int
    event_type: str
    actor_type: str | None
    actor_name: str | None
    correlation_id: str | None
    payload: dict | None
    created_at: datetime


class AgentRunResponse(BaseModel):
    id: int
    user_message_id: int
    assistant_message_id: int | None
    status: AgentRunStatus
    final_answer: str | None
    context_metrics: dict | None
    error: str | None
    ended_at: datetime | None
    created_at: datetime
    events: list[AgentEventResponse] = []


class MessageResponse(BaseModel):
    id: int
    role: MessageRole
    content: str
    agent_runs: list[AgentRunResponse] = []
    created_at: datetime


class ConversationCreate(BaseModel):
    title: str


class ConversationResponse(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationMessagesResponse(ConversationResponse):
    messages: list[MessageResponse]
