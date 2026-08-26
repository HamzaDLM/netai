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


class PromptPreviewCreate(MessageCreate):
    include_draft: bool = True
    user_message_id: int | None = None


class PromptSnapshotMessageResponse(BaseModel):
    index: int
    role: str
    source: str
    text: str
    estimated_tokens: int
    message_id: int | None = None
    summary_id: int | None = None
    up_to_message_id: int | None = None


class PromptSnapshotResponse(BaseModel):
    messages: list[PromptSnapshotMessageResponse]
    metrics: dict


class ChatUserSettingsUpdate(BaseModel):
    custom_instructions: str | None = None


class ChatUserSettingsResponse(BaseModel):
    custom_instructions: str


class ConversationAttachmentCreate(BaseModel):
    filename: str
    content: str
    content_type: str | None = None


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
    latency_ms: int | None
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


class AgentEventResponse(ORMBaseModel):
    id: int
    event_sequence: int
    event_type: str
    actor_type: str | None
    actor_name: str | None
    correlation_id: str | None
    payload: dict
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
    events: list[AgentEventResponse] = []
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
    events: list[AgentEventResponse] = []
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


class ConversationAttachmentResponse(ORMBaseModel):
    id: int
    conversation_id: str
    filename: str
    content_type: str | None
    size_bytes: int
    estimated_tokens: int
    truncated: bool
    active: bool
    created_at: datetime
    updated_at: datetime


class ConversationResponse(ORMBaseModel):
    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationMessagesResponse(ConversationResponse):
    messages: list[MessageResponse]


class AdminFeedbackConversationResponse(ORMBaseModel):
    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class AdminFeedbackItemResponse(BaseModel):
    feedback: FeedbackResponse
    conversation: AdminFeedbackConversationResponse
    user_message: MessageResponse | None
    assistant_message: MessageResponse


class AdminOverviewResponse(BaseModel):
    window_started_at: datetime
    generated_at: datetime
    conversations: int
    user_messages: int
    tool_calls_total: int
    tool_calls_failed: int
    average_latency_ms: float | None
    feedback_total: int
    negative_feedback: int
