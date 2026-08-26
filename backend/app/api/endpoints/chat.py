import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from haystack.dataclasses import ChatMessage
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    AsyncSessionDep,
    CheckUserSSODep,
    NetAIServiceDep,
    RequestIDDep,
)
from app.api.models.chat import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    AgentType,
    Conversation,
    ConversationAttachment,
    Feedback,
    Message,
    MessageRole,
    ToolCall,
    ToolCallStatus,
)
from app.api.models.skills import Skill
from app.api.models.users import User as UserModel
from app.api.models.users import UserRole
from app.api.schemas.chat import (
    AdminFeedbackConversationResponse,
    AdminFeedbackItemResponse,
    AdminOverviewResponse,
    ChatUserSettingsResponse,
    ChatUserSettingsUpdate,
    ConversationAttachmentCreate,
    ConversationAttachmentResponse,
    ConversationCreate,
    ConversationMessagesResponse,
    ConversationResponse,
    FeedbackCreate,
    FeedbackResponse,
    MessageCreate,
    MessageResponse,
    PromptPreviewCreate,
    PromptSnapshotResponse,
)
from app.core.config import project_settings
from app.db.session import SessionLocal
from app.prompts import TITLE_GENERATION_PROMPT
from app.services.chat_agent import (
    AgentPromptSnapshot,
    PromptSnapshotMessage,
    build_agent_prompt_snapshot,
    run_agent,
    run_agent_stream,
)
from app.services.chat_attachments import (
    get_active_attachment_count,
    get_active_attachment_total_chars,
    list_active_attachments,
    parse_attachment_payload,
)
from app.services.netai import NetAIService

router = APIRouter(prefix="/llm", tags=["chat"])
logger = logging.getLogger(__name__)
_SKILL_COMMAND_RE = re.compile(r"/([a-z0-9][a-z0-9-]{0,79})(?=$|\s)", re.IGNORECASE)
_ARTIFACT_EVENT_TYPES = {
    "artifact_snapshot",
    "artifact_delta",
}
_TOOL_LIFECYCLE_EVENT_TYPES = {
    "tool_started",
    "tool_completed",
    "tool_failed",
}
_DURABLE_AGENT_EVENT_TYPES = _ARTIFACT_EVENT_TYPES | _TOOL_LIFECYCLE_EVENT_TYPES
_STREAMED_AGENT_EVENT_TYPES = _DURABLE_AGENT_EVENT_TYPES | {
    "run_started",
    "run_finished",
    "run_error",
}
_EVENT_ENVELOPE_KEYS = {
    "type",
    "event_id",
    "event_sequence",
    "run_id",
    "conversation_id",
    "emitted_at",
}


def _event_actor(event: dict[str, Any]) -> tuple[str | None, str | None]:
    event_type = str(event.get("type", "")).strip()
    if not event_type:
        return None, None
    if event_type in _TOOL_LIFECYCLE_EVENT_TYPES:
        return "tool", str(event.get("tool_name") or "unknown_tool")
    if event_type in _ARTIFACT_EVENT_TYPES:
        artifact = event.get("artifact")
        artifact_kind = artifact.get("kind") if isinstance(artifact, dict) else None
        return "tool", str(event.get("kind") or artifact_kind or "artifact")
    return "system", event_type


def _agent_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in event.items() if key not in _EVENT_ENVELOPE_KEYS
    }


def _agent_event_correlation_id(event: dict[str, Any]) -> str | None:
    for key in ("artifact_id", "tool_call_id"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    artifact = event.get("artifact")
    if isinstance(artifact, dict):
        value = artifact.get("id")
        if isinstance(value, str) and value:
            return value
    event_id = event.get("event_id")
    if isinstance(event_id, str) and event_id:
        return event_id
    return None


def _completed_run_debug_snapshot(
    snapshot: AgentPromptSnapshot,
    *,
    run: AgentRun,
    service: NetAIService,
) -> AgentPromptSnapshot:
    """Enrich pre-snapshot runs using their durable tool evidence and response."""

    group_prompts: dict[str, str] = {}
    for tool_call in run.tool_calls:
        resolved = service.tool_group_prompt_for_tool(tool_call.tool_name)
        if resolved is not None:
            connector, prompt = resolved
            group_prompts.setdefault(connector, prompt)

    if group_prompts:
        blocks = "\n\n".join(
            f"Tool group guidance [{connector}]\n\n{prompt}"
            for connector, prompt in sorted(group_prompts.items())
        )
        system_message = next(
            (message for message in snapshot.messages if message.role == "system"),
            None,
        )
        if system_message is not None and blocks not in system_message.text:
            system_message.text = f"{system_message.text}\n\n{blocks}".strip()
            system_message.estimated_tokens = max(1, len(system_message.text) // 4)

    for tool_call in run.tool_calls:
        text = json.dumps(
            {
                "tool_name": tool_call.tool_name,
                "input": tool_call.input_params,
                "output": tool_call.output,
                "status": tool_call.status.value,
                "error": tool_call.error_message,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        snapshot.messages.append(
            PromptSnapshotMessage(
                index=len(snapshot.messages),
                role="tool",
                source="tool_result",
                text=text,
                estimated_tokens=max(1, len(text) // 4),
            )
        )

    if run.final_answer:
        snapshot.messages.append(
            PromptSnapshotMessage(
                index=len(snapshot.messages),
                role="assistant",
                source="assistant_response",
                text=run.final_answer,
                estimated_tokens=max(1, len(run.final_answer) // 4),
            )
        )
    return snapshot


def _as_tool_status(value: Any) -> ToolCallStatus:
    lowered = str(value or "success").strip().lower()
    if lowered in {"success", "completed", "ok"}:
        return ToolCallStatus.success
    if lowered in {"timeout", "timed_out"}:
        return ToolCallStatus.timeout
    if lowered in {"blocked", "requires_approval"}:
        return ToolCallStatus.blocked
    if lowered in {"error", "failed", "failure"}:
        return ToolCallStatus.error
    if lowered == "running":
        return ToolCallStatus.running
    return ToolCallStatus.success


def _as_run_status(value: Any) -> AgentRunStatus:
    lowered = str(value or "completed").strip().lower()
    if lowered in {"completed", "success", "ok"}:
        return AgentRunStatus.completed
    if lowered in {"error", "failed", "failure", "timeout", "blocked"}:
        return AgentRunStatus.failed
    return AgentRunStatus.completed


def _coerce_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"value": value}


def _derive_times(duration_ms: Any) -> tuple[datetime, datetime]:
    ended_at = datetime.now(timezone.utc)
    if isinstance(duration_ms, int) and duration_ms > 0:
        started_at = ended_at - timedelta(milliseconds=duration_ms)
        return started_at, ended_at
    return ended_at, ended_at


def _normalize_custom_instructions(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


async def _get_or_create_user_record(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> UserModel:
    record = await db.get(UserModel, user.id)
    if record is not None:
        return record

    record = UserModel(
        id=user.id,
        username=user.username,
        role=user.role,
        custom_instructions=None,
    )
    db.add(record)
    await db.flush()
    return record


def _message_load_options():
    return [
        selectinload(Message.agent_runs).selectinload(AgentRun.sub_agent_calls),
        selectinload(Message.agent_runs).selectinload(AgentRun.tool_calls),
        selectinload(Message.agent_runs).selectinload(AgentRun.events),
        selectinload(Message.agent_runs)
        .selectinload(AgentRun.child_runs)
        .selectinload(AgentRun.tool_calls),
        selectinload(Message.agent_runs)
        .selectinload(AgentRun.child_runs)
        .selectinload(AgentRun.events),
        selectinload(Message.feedback),
    ]


async def _get_active_conversation(
    db: AsyncSessionDep, conversation_id: str
) -> Conversation:
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.archived.is_(False),
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return conversation


def _extract_requested_skill_slugs(content: str) -> tuple[list[str], str]:
    stripped = content.strip()
    if not stripped:
        return [], ""

    leading_offset = len(content) - len(content.lstrip())
    cursor = leading_offset
    seen: set[str] = set()
    slugs: list[str] = []
    matched_any = False

    while cursor < len(content):
        match = _SKILL_COMMAND_RE.match(content[cursor:])
        if not match:
            break

        slug = str(match.group(1) or "").strip().lower()
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
        matched_any = True
        cursor += match.end()

        while cursor < len(content) and content[cursor].isspace():
            cursor += 1

        if cursor >= len(content) or content[cursor] != "/":
            break

    if not matched_any:
        return [], stripped

    return slugs, content[cursor:].strip()


async def _load_requested_skills(
    *,
    db: AsyncSessionDep,
    user_id: int,
    content: str,
) -> tuple[list[dict[str, str]], str]:
    requested_slugs, normalized_question = _extract_requested_skill_slugs(content)
    if not requested_slugs:
        return [], content.strip()

    stmt = (
        select(Skill)
        .where(
            Skill.user_id == user_id,
            Skill.archived.is_(False),
            Skill.enabled.is_(True),
            Skill.slug.in_(requested_slugs),
        )
        .order_by(Skill.created_at.asc())
    )
    result = await db.execute(stmt)
    skills = result.scalars().all()
    skills_by_slug = {
        str(skill.slug or "").strip().lower(): skill
        for skill in skills
        if str(skill.instructions or "").strip()
    }
    missing = [slug for slug in requested_slugs if slug not in skills_by_slug]
    if missing:
        return [], content.strip()

    return (
        [
            {
                "name": str(skills_by_slug[slug].name or "").strip(),
                "instructions": str(skills_by_slug[slug].instructions or "").strip(),
            }
            for slug in requested_slugs
        ],
        normalized_question,
    )


async def _persist_run_graph(
    *,
    db: AsyncSessionDep,
    conversation_id: str,
    user_message_id: int,
    assistant_message_id: int,
    assistant_content: str,
    context_metrics: dict[str, Any] | None,
    prompt_snapshot: dict[str, Any] | None,
    run_map: dict[str, Any] | None,
) -> AgentRun:
    agent_map = run_map.get("agent") if isinstance(run_map, dict) else {}
    if not isinstance(agent_map, dict):
        agent_map = {}
    tool_calls = run_map.get("tool_calls") if isinstance(run_map, dict) else []
    if not isinstance(tool_calls, list):
        tool_calls = []

    agent_status = _as_run_status(agent_map.get("status"))
    started_at, ended_at = _derive_times(agent_map.get("duration_ms"))
    agent_run = AgentRun(
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        parent_run_id=None,
        agent_type=AgentType.orchestrator,
        agent_name=str(agent_map.get("agent_name") or "netai"),
        depth=0,
        status=agent_status,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=agent_map.get("duration_ms")
        if isinstance(agent_map.get("duration_ms"), int)
        else None,
        final_answer=assistant_content,
        context_metrics=context_metrics,
        prompt_snapshot=prompt_snapshot,
        error=str(agent_map.get("error"))
        if agent_status == AgentRunStatus.failed and agent_map.get("error") is not None
        else None,
    )
    db.add(agent_run)
    await db.flush()

    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        output = _coerce_json_dict(tool_call.get("output"))
        db.add(
            ToolCall(
                run_id=agent_run.id,
                conversation_id=conversation_id,
                tool_name=str(tool_call.get("tool_name") or "unknown_tool"),
                input_params=_coerce_json_dict(tool_call.get("input_params")),
                output=output,
                latency_ms=tool_call.get("latency_ms")
                if isinstance(tool_call.get("latency_ms"), int)
                else None,
                status=_as_tool_status(tool_call.get("status")),
                error_type=str(tool_call.get("error_type"))
                if tool_call.get("error_type") is not None
                else None,
                error_message=str(tool_call.get("error_message"))
                if tool_call.get("error_message") is not None
                else None,
            )
        )

    return agent_run


async def _generate_title_if_missing(
    service: NetAIService,
    conversation_id: str,
    user_question: str,
    assistant_content: str,
) -> None:
    async with SessionLocal() as title_db:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.archived.is_(False),
        )
        result = await title_db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if not conversation or conversation.title:
            return

        try:
            llm_result = await service.generate(
                [
                    ChatMessage.from_system(TITLE_GENERATION_PROMPT),
                    ChatMessage.from_user(
                        f"user question: {user_question} \n LLM assistant answer: {assistant_content}"
                    ),
                ]
            )
            replies = llm_result.get("replies")
            first_reply = replies[0] if isinstance(replies, list) and replies else None
            title = (
                (first_reply.text or "").strip()
                if isinstance(first_reply, ChatMessage)
                else ""
            )
            if not title:
                return
            conversation.title = title
            await title_db.commit()
            await title_db.refresh(conversation)
        except Exception as exc:
            await title_db.rollback()
            logger.warning("Conversation title generation failed: %s", exc)


async def _get_active_attachment(
    *,
    db: AsyncSessionDep,
    conversation_id: str,
    attachment_id: int,
) -> ConversationAttachment:
    stmt = select(ConversationAttachment).where(
        ConversationAttachment.id == attachment_id,
        ConversationAttachment.conversation_id == conversation_id,
        ConversationAttachment.active.is_(True),
    )
    result = await db.execute(stmt)
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return attachment


@router.post("/conversation", response_model=ConversationResponse)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    conversation = Conversation(title=payload.title, user_id=user.id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("/settings/chat", response_model=ChatUserSettingsResponse)
async def get_chat_settings(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    record = await _get_or_create_user_record(db, user)
    custom_instructions = record.custom_instructions or ""
    await db.commit()
    return ChatUserSettingsResponse(custom_instructions=custom_instructions)


@router.patch("/settings/chat", response_model=ChatUserSettingsResponse)
async def update_chat_settings(
    payload: ChatUserSettingsUpdate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    record = await _get_or_create_user_record(db, user)
    record.custom_instructions = _normalize_custom_instructions(
        payload.custom_instructions
    )
    await db.commit()
    await db.refresh(record)
    return ChatUserSettingsResponse(
        custom_instructions=record.custom_instructions or ""
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
    search: str | None = None,
):
    normalized_search = (search or "").strip()
    stmt = (
        select(Conversation)
        .where(
            Conversation.archived.is_(False),
            Conversation.user_id == user.id,
        )
        .order_by(Conversation.updated_at.desc())
    )
    if normalized_search:
        pattern = f"%{normalized_search}%"
        user_message_match = (
            select(Message.id)
            .where(
                Message.conversation_id == Conversation.id,
                Message.archived.is_(False),
                Message.role == MessageRole.user,
                Message.content.ilike(pattern),
            )
            .exists()
        )
        stmt = stmt.where(
            or_(
                Conversation.title.ilike(pattern),
                user_message_match,
            )
        )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get(
    "/conversation/{conversation_id}", response_model=ConversationMessagesResponse
)
async def get_conversation(
    conversation_id: str,
    db: AsyncSessionDep,
):
    stmt = (
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.archived.is_(False),
        )
        .options(
            selectinload(Conversation.messages)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.sub_agent_calls),
            selectinload(Conversation.messages)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.tool_calls),
            selectinload(Conversation.messages)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.events),
            selectinload(Conversation.messages)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.child_runs)
            .selectinload(AgentRun.tool_calls),
            selectinload(Conversation.messages)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.child_runs)
            .selectinload(AgentRun.events),
            selectinload(Conversation.messages).selectinload(Message.feedback),
        )
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return conversation


@router.get("/admin/feedbacks", response_model=list[AdminFeedbackItemResponse])
async def list_admin_feedbacks(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
    limit: int = 100,
):
    if user.role not in {UserRole.admin, UserRole.superuser}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    bounded_limit = min(max(limit, 1), 250)
    has_comment = Feedback.comment.is_not(None) & (func.trim(Feedback.comment) != "")
    stmt = (
        select(Feedback)
        .join(Feedback.message)
        .join(Message.conversation)
        .where(
            Message.archived.is_(False),
            Conversation.archived.is_(False),
            or_(
                Feedback.rating == "bad",
                Feedback.feedback_type.is_not(None),
                has_comment,
            ),
        )
        .options(
            selectinload(Feedback.message).selectinload(Message.conversation),
            selectinload(Feedback.message)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.user_message),
            selectinload(Feedback.message)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.sub_agent_calls),
            selectinload(Feedback.message)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.tool_calls),
            selectinload(Feedback.message)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.events),
            selectinload(Feedback.message)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.child_runs)
            .selectinload(AgentRun.tool_calls),
            selectinload(Feedback.message)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.child_runs)
            .selectinload(AgentRun.events),
            selectinload(Feedback.message).selectinload(Message.feedback),
        )
        .order_by(Feedback.updated_at.desc())
        .limit(bounded_limit)
    )
    result = await db.execute(stmt)
    feedback_rows = result.scalars().all()

    items: list[AdminFeedbackItemResponse] = []
    for feedback in feedback_rows:
        assistant_message = feedback.message
        user_message = None
        for run in assistant_message.agent_runs or []:
            if run.user_message is not None:
                user_message = run.user_message
                break
        user_message_response = (
            MessageResponse(
                id=user_message.id,
                role=user_message.role,
                content=user_message.content,
                agent_runs=[],
                feedback=[],
                created_at=user_message.created_at,
                updated_at=user_message.updated_at,
            )
            if user_message is not None
            else None
        )
        items.append(
            AdminFeedbackItemResponse(
                feedback=FeedbackResponse.model_validate(feedback),
                conversation=AdminFeedbackConversationResponse.model_validate(
                    assistant_message.conversation
                ),
                user_message=user_message_response,
                assistant_message=MessageResponse.model_validate(assistant_message),
            )
        )

    return items


@router.get("/admin/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    if user.role not in {UserRole.admin, UserRole.superuser}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    generated_at = datetime.now(timezone.utc)
    window_started_at = generated_at - timedelta(days=7)
    active_conversation = Conversation.archived.is_(False)
    active_message = Message.archived.is_(False)

    conversations = (
        select(func.count(Conversation.id))
        .where(
            active_conversation,
            Conversation.created_at >= window_started_at,
        )
        .scalar_subquery()
    )
    user_messages = (
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            active_conversation,
            active_message,
            Message.role == MessageRole.user,
            Message.created_at >= window_started_at,
        )
        .scalar_subquery()
    )
    tool_calls_total = (
        select(func.count(ToolCall.id))
        .join(Conversation, Conversation.id == ToolCall.conversation_id)
        .where(
            active_conversation,
            ToolCall.created_at >= window_started_at,
        )
        .scalar_subquery()
    )
    tool_calls_failed = (
        select(func.count(ToolCall.id))
        .join(Conversation, Conversation.id == ToolCall.conversation_id)
        .where(
            active_conversation,
            ToolCall.created_at >= window_started_at,
            ToolCall.status.in_([ToolCallStatus.error, ToolCallStatus.timeout]),
        )
        .scalar_subquery()
    )
    average_latency_ms = (
        select(func.avg(AgentRun.duration_ms))
        .join(Conversation, Conversation.id == AgentRun.conversation_id)
        .where(
            active_conversation,
            AgentRun.depth == 0,
            AgentRun.duration_ms.is_not(None),
            AgentRun.created_at >= window_started_at,
        )
        .scalar_subquery()
    )
    feedback_total = (
        select(func.count(Feedback.id))
        .join(Message, Message.id == Feedback.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            active_conversation,
            active_message,
            Feedback.created_at >= window_started_at,
        )
        .scalar_subquery()
    )
    negative_feedback = (
        select(func.count(Feedback.id))
        .join(Message, Message.id == Feedback.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            active_conversation,
            active_message,
            Feedback.rating == "bad",
            Feedback.created_at >= window_started_at,
        )
        .scalar_subquery()
    )

    result = await db.execute(
        select(
            conversations.label("conversations"),
            user_messages.label("user_messages"),
            tool_calls_total.label("tool_calls_total"),
            tool_calls_failed.label("tool_calls_failed"),
            average_latency_ms.label("average_latency_ms"),
            feedback_total.label("feedback_total"),
            negative_feedback.label("negative_feedback"),
        )
    )
    row = result.one()
    average_latency = row.average_latency_ms
    return AdminOverviewResponse(
        window_started_at=window_started_at,
        generated_at=generated_at,
        conversations=int(row.conversations or 0),
        user_messages=int(row.user_messages or 0),
        tool_calls_total=int(row.tool_calls_total or 0),
        tool_calls_failed=int(row.tool_calls_failed or 0),
        average_latency_ms=(
            float(average_latency) if average_latency is not None else None
        ),
        feedback_total=int(row.feedback_total or 0),
        negative_feedback=int(row.negative_feedback or 0),
    )


@router.get(
    "/conversation/{conversation_id}/attachments",
    response_model=list[ConversationAttachmentResponse],
)
async def list_conversation_attachments(
    conversation_id: str,
    db: AsyncSessionDep,
):
    await _get_active_conversation(db, conversation_id)
    return await list_active_attachments(db, conversation_id=conversation_id)


@router.post(
    "/conversation/{conversation_id}/attachments",
    response_model=ConversationAttachmentResponse,
)
async def create_conversation_attachment(
    conversation_id: str,
    payload: ConversationAttachmentCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    _ = user
    await _get_active_conversation(db, conversation_id)

    try:
        parsed = parse_attachment_payload(
            filename=payload.filename,
            content=payload.content,
            content_type=payload.content_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    attachment_count = await get_active_attachment_count(
        db, conversation_id=conversation_id
    )
    if attachment_count >= project_settings.CHAT_ATTACHMENT_MAX_COUNT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="attachment_limit_reached",
        )

    total_chars = await get_active_attachment_total_chars(
        db, conversation_id=conversation_id
    )
    if (
        total_chars + len(parsed.content_text)
        > project_settings.CHAT_ATTACHMENT_MAX_TOTAL_CHARS
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="attachment_total_size_exceeded",
        )

    attachment = ConversationAttachment(
        conversation_id=conversation_id,
        filename=parsed.filename,
        content_type=parsed.content_type,
        size_bytes=parsed.size_bytes,
        estimated_tokens=parsed.estimated_tokens,
        truncated=parsed.truncated,
        active=True,
        content_sha256=parsed.content_sha256,
        content_text=parsed.content_text,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)
    return attachment


@router.delete(
    "/conversation/{conversation_id}/attachments/{attachment_id}",
    response_model=ConversationAttachmentResponse,
)
async def delete_conversation_attachment(
    conversation_id: str,
    attachment_id: int,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    _ = user
    attachment = await _get_active_attachment(
        db=db,
        conversation_id=conversation_id,
        attachment_id=attachment_id,
    )
    attachment.active = False
    await db.commit()
    await db.refresh(attachment)
    return attachment


@router.post("/conversation/{conversation_id}/message", response_model=MessageResponse)
async def ask_llm(
    conversation_id: str,
    payload: MessageCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
    service: NetAIServiceDep,
    request_id: RequestIDDep,
):
    await _get_active_conversation(db, conversation_id)
    user_record = await _get_or_create_user_record(db, user)
    custom_instructions = user_record.custom_instructions
    requested_skills, question_for_agent = await _load_requested_skills(
        db=db,
        user_id=user.id,
        content=payload.content,
    )

    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )
    db.add(user_message)
    await db.flush()
    user_message_id = user_message.id
    await db.commit()

    run_agent_kwargs: dict[str, Any] = {
        "service": service,
        "conversation_id": conversation_id,
        "question": question_for_agent,
        "user_id": user.id,
        "request_id": request_id,
        "skills": requested_skills or None,
    }
    if custom_instructions:
        run_agent_kwargs["custom_instructions"] = custom_instructions
    agent_result = await run_agent(**run_agent_kwargs)

    assistant_content = str(agent_result.get("answer") or "")
    context_metrics_value = agent_result.get("context_metrics")
    context_metrics = (
        context_metrics_value if isinstance(context_metrics_value, dict) else None
    )
    run_map_value = agent_result.get("run_map")
    run_map = run_map_value if isinstance(run_map_value, dict) else None
    prompt_snapshot_value = agent_result.get("prompt_snapshot")
    prompt_snapshot = (
        prompt_snapshot_value if isinstance(prompt_snapshot_value, dict) else None
    )
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        token_input=(
            int(context_metrics.get("used_tokens", 0))
            if context_metrics is not None
            else None
        ),
    )
    db.add(assistant_message)
    await db.flush()
    assistant_message_id = assistant_message.id

    await _persist_run_graph(
        db=db,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        assistant_content=assistant_content,
        context_metrics=context_metrics,
        prompt_snapshot=prompt_snapshot,
        run_map=run_map,
    )

    await db.commit()

    await _generate_title_if_missing(
        service=service,
        conversation_id=conversation_id,
        user_question=payload.content,
        assistant_content=assistant_content,
    )

    hydrated_stmt = (
        select(Message)
        .where(Message.id == assistant_message_id)
        .options(*_message_load_options())
    )
    hydrated_result = await db.execute(hydrated_stmt)
    hydrated_message = hydrated_result.scalar_one_or_none()
    if hydrated_message:
        return hydrated_message

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="assistant_message_hydration_failed",
    )


@router.post(
    "/conversation/{conversation_id}/prompt-preview",
    response_model=PromptSnapshotResponse,
)
async def preview_llm_prompt(
    conversation_id: str,
    payload: PromptPreviewCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
    service: NetAIServiceDep,
):
    await _get_active_conversation(db, conversation_id)
    completed_run: AgentRun | None = None
    if not payload.include_draft:
        stored_snapshot_stmt = (
            select(AgentRun)
            .join(Message, AgentRun.user_message_id == Message.id)
            .where(
                AgentRun.conversation_id == conversation_id,
                Message.archived.is_(False),
                *(
                    (AgentRun.user_message_id == payload.user_message_id,)
                    if payload.user_message_id is not None
                    else (Message.content == payload.content,)
                ),
            )
            .options(selectinload(AgentRun.tool_calls))
            .order_by(AgentRun.id.desc())
            .limit(1)
        )
        stored_snapshot_result = await db.execute(stored_snapshot_stmt)
        completed_run = stored_snapshot_result.scalar_one_or_none()
        if completed_run is not None and isinstance(
            completed_run.prompt_snapshot, dict
        ):
            return completed_run.prompt_snapshot

    user_record = await _get_or_create_user_record(db, user)
    requested_skills, question_for_agent = await _load_requested_skills(
        db=db,
        user_id=user.id,
        content=payload.content,
    )
    snapshot = await build_agent_prompt_snapshot(
        service=service,
        conversation_id=conversation_id,
        question=question_for_agent,
        skills=requested_skills or None,
        custom_instructions=user_record.custom_instructions,
        include_draft_question=payload.include_draft,
    )
    if completed_run is not None:
        snapshot = _completed_run_debug_snapshot(
            snapshot,
            run=completed_run,
            service=service,
        )
    return {
        "messages": [asdict(message) for message in snapshot.messages],
        "metrics": snapshot.metrics,
    }


@router.post("/conversation/{conversation_id}/message/stream")
async def ask_llm_stream(
    conversation_id: str,
    payload: MessageCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
    service: NetAIServiceDep,
    request_id: RequestIDDep,
):
    await _get_active_conversation(db, conversation_id)
    user_record = await _get_or_create_user_record(db, user)
    custom_instructions = user_record.custom_instructions
    requested_skills, question_for_agent = await _load_requested_skills(
        db=db,
        user_id=user.id,
        content=payload.content,
    )

    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )
    db.add(user_message)
    await db.flush()
    user_message_id = user_message.id
    await db.commit()

    async def event_generator() -> AsyncIterator[str]:
        assistant_tokens: list[str] = []
        assistant_char_count = 0
        context_metrics: dict[str, Any] | None = None
        run_map: dict[str, Any] | None = None
        prompt_snapshot: dict[str, Any] | None = None
        final_answer: str | None = None
        durable_events: list[dict[str, Any]] = []
        run_agent_stream_kwargs: dict[str, Any] = {
            "service": service,
            "conversation_id": conversation_id,
            "question": question_for_agent,
            "user_id": user.id,
            "request_id": request_id,
            "skills": requested_skills or None,
        }
        if custom_instructions:
            run_agent_stream_kwargs["custom_instructions"] = custom_instructions

        async for event in run_agent_stream(**run_agent_stream_kwargs):
            event_type = str(event.get("type") or "")
            if event_type == "token":
                token = str(event.get("token") or "")
                assistant_tokens.append(token)
                assistant_char_count += len(token)
                yield f"event: assistant_token\ndata: {json.dumps({'token': token})}\n\n"
                continue
            if event_type == "context_metrics":
                context_metrics = event
                yield f"event: context_metrics\ndata: {json.dumps(event)}\n\n"
                continue
            if event_type == "run_map":
                maybe_map = event.get("run_map")
                if isinstance(maybe_map, dict):
                    run_map = maybe_map
                maybe_snapshot = event.get("prompt_snapshot")
                if isinstance(maybe_snapshot, dict):
                    prompt_snapshot = maybe_snapshot
                answer_value = event.get("answer")
                if isinstance(answer_value, str) and answer_value:
                    final_answer = answer_value
                continue

            if event_type in _STREAMED_AGENT_EVENT_TYPES:
                client_event = {
                    **event,
                    "assistant_offset": assistant_char_count,
                }
                if event_type in _DURABLE_AGENT_EVENT_TYPES:
                    durable_events.append(client_event)
                yield f"event: {event_type}\ndata: {json.dumps(client_event)}\n\n"

        assistant_content = "".join(assistant_tokens).strip()
        if not assistant_content and isinstance(final_answer, str):
            assistant_content = final_answer

        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_content,
            token_input=(
                int(context_metrics.get("used_tokens", 0))
                if isinstance(context_metrics, dict)
                else None
            ),
        )
        db.add(assistant_message)
        await db.flush()
        assistant_message_id = assistant_message.id

        agent_run = await _persist_run_graph(
            db=db,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            assistant_content=assistant_content,
            context_metrics=context_metrics
            if isinstance(context_metrics, dict)
            else None,
            prompt_snapshot=prompt_snapshot,
            run_map=run_map,
        )

        for event in durable_events:
            event_sequence = event.get("event_sequence")
            if not isinstance(event_sequence, int):
                continue
            actor_type, actor_name = _event_actor(event)
            db.add(
                AgentEvent(
                    run_id=agent_run.id,
                    event_sequence=event_sequence,
                    event_type=str(event.get("type") or "unknown"),
                    actor_type=actor_type,
                    actor_name=actor_name,
                    correlation_id=_agent_event_correlation_id(event),
                    payload=_agent_event_payload(event),
                )
            )

        await db.commit()
        agent_duration_ms = None
        if isinstance(run_map, dict):
            agent = run_map.get("agent")
            if isinstance(agent, dict) and isinstance(agent.get("duration_ms"), int):
                agent_duration_ms = agent.get("duration_ms")

        yield (
            "event: done\ndata: "
            + json.dumps(
                {
                    "message_id": assistant_message_id,
                    "duration_ms": agent_duration_ms,
                }
            )
            + "\n\n"
        )

        asyncio.create_task(
            _generate_title_if_missing(
                service=service,
                conversation_id=conversation_id,
                user_question=payload.content,
                assistant_content=assistant_content,
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: int,
    payload: FeedbackCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    message = await db.get(Message, message_id)
    if not message or message.archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if message.role != MessageRole.assistant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="feedback_only_supported_for_assistant_messages",
        )

    requested_types: list[Any] = []
    if payload.feedback_types:
        requested_types.extend(payload.feedback_types)
    elif payload.feedback_type is not None:
        requested_types.append(payload.feedback_type)

    # Replace this user's feedback set for the message to keep writes idempotent.
    await db.execute(
        delete(Feedback).where(
            Feedback.message_id == message_id,
            Feedback.user_id == user.id,
        )
    )

    unique_feedback_types: list[Any] = []
    seen_feedback_types: set[str] = set()
    for feedback_type in requested_types:
        key = str(feedback_type)
        if key in seen_feedback_types:
            continue
        seen_feedback_types.add(key)
        unique_feedback_types.append(feedback_type)

    feedback_rows = unique_feedback_types or [None]
    for feedback_type in feedback_rows:
        db.add(
            Feedback(
                message_id=message_id,
                user_id=user.id,
                rating=payload.rating,
                feedback_type=feedback_type,
                comment=payload.comment,
            )
        )
    await db.commit()


@router.patch("/conversation/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: str,
    payload: ConversationCreate,
    db: AsyncSessionDep,
):
    conversation = await _get_active_conversation(db, conversation_id)
    conversation.title = payload.title
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.delete(
    "/conversation/mark/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def mark_deleted_conversation(
    conversation_id: str,
    db: AsyncSessionDep,
):
    conversation = await _get_active_conversation(db, conversation_id)
    conversation.archived = True
    await db.commit()


@router.delete(
    "/conversation/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSessionDep,
):
    conversation = await _get_active_conversation(db, conversation_id)
    conversation.archived = True
    await db.commit()
