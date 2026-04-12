from datetime import datetime

from pydantic import BaseModel

from app.api.models.chat import MessageRole


class MessageCreate(BaseModel):
    content: str


class FeedbackCreate(BaseModel):
    rating: str
    comment: str | None = None


class EvidenceResponse(BaseModel):
    id: int
    source_type: str
    source_ref: str | None
    content_snippet: str
    score: float | None
    timestamp: datetime | None


class ToolCallResponse(BaseModel):
    id: int
    tool_name: str
    tool_source: str | None
    arguments: dict | None
    result: dict | None
    latency_ms: int | None
    evidence_items: list[EvidenceResponse]


class MessageResponse(BaseModel):
    id: int
    role: MessageRole
    content: str
    tool_calls: list[ToolCallResponse] = []
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
