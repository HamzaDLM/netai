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
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    AsyncSessionDep,
    ChatRunCoordinatorDep,
    CheckUserSSODep,
    NetAIServiceDep,
    RequestIDDep,
)
from app.api.models.chat import (
    AgentRun,
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
    AdminFeedbackResponse,
    AdminMessageVolumePoint,
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
from app.core.security import User
from app.services.chat_agent import (
    AgentPromptSnapshot,
    PromptSnapshotMessage,
    build_agent_prompt_snapshot,
)
from app.services.chat_attachments import (
    get_active_attachment_count,
    get_active_attachment_total_chars,
    list_active_attachments,
    parse_attachment_payload,
)
from app.services.chat_runs import (
    ActiveConversationRunError,
    ChatRunCoordinator,
    ChatRunRequest,
    StartedChatRun,
    sse_event,
)
from app.services.netai import NetAIService

router = APIRouter(prefix="/llm", tags=["chat"])
logger = logging.getLogger(__name__)
_SKILL_COMMAND_RE = re.compile(r"/([a-z0-9][a-z0-9-]{0,79})(?=$|\s)", re.IGNORECASE)


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


async def _start_durable_chat_run(
    *,
    coordinator: ChatRunCoordinator,
    conversation_id: str,
    content: str,
    db: AsyncSessionDep,
    user: User,
    request_id: str,
) -> StartedChatRun:
    await _get_active_conversation(db, conversation_id)
    user_record = await _get_or_create_user_record(db, user)
    requested_skills, question_for_agent = await _load_requested_skills(
        db=db,
        user_id=user.id,
        content=content,
    )
    custom_instructions = user_record.custom_instructions
    await db.commit()

    try:
        return await coordinator.start(
            ChatRunRequest(
                conversation_id=conversation_id,
                raw_question=content,
                agent_question=question_for_agent,
                user_id=user.id,
                request_id=request_id,
                skills=requested_skills or None,
                custom_instructions=custom_instructions,
            )
        )
    except ActiveConversationRunError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "conversation_run_active", "run_id": exc.run_id},
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc


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
    reviewable_feedback = or_(
        Feedback.rating == "bad",
        Feedback.feedback_type.is_not(None),
        has_comment,
    )
    submissions_stmt = (
        select(
            Feedback.message_id,
            Feedback.user_id,
            func.max(Feedback.updated_at).label("last_updated_at"),
        )
        .join(Feedback.message)
        .join(Message.conversation)
        .where(
            Message.archived.is_(False),
            Conversation.archived.is_(False),
            reviewable_feedback,
        )
        .group_by(Feedback.message_id, Feedback.user_id)
        .order_by(func.max(Feedback.updated_at).desc())
        .limit(bounded_limit)
    )
    submission_rows = (await db.execute(submissions_stmt)).all()
    if not submission_rows:
        return []

    submission_keys = [(row.message_id, row.user_id) for row in submission_rows]
    stmt = (
        select(Feedback)
        .where(
            or_(
                *(
                    and_(
                        Feedback.message_id == message_id,
                        Feedback.user_id == user_id,
                    )
                    for message_id, user_id in submission_keys
                )
            )
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
        .order_by(Feedback.id.asc())
    )
    result = await db.execute(stmt)
    feedback_rows = result.scalars().all()
    feedback_by_submission: dict[tuple[int, int], list[Feedback]] = {}
    for feedback in feedback_rows:
        feedback_by_submission.setdefault(
            (feedback.message_id, feedback.user_id), []
        ).append(feedback)

    items: list[AdminFeedbackItemResponse] = []
    for submission_key in submission_keys:
        submission_feedback = feedback_by_submission.get(submission_key, [])
        if not submission_feedback:
            continue
        feedback = submission_feedback[0]
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
                feedback=AdminFeedbackResponse(
                    **FeedbackResponse.model_validate(feedback).model_dump(),
                    feedback_types=[
                        row.feedback_type
                        for row in submission_feedback
                        if row.feedback_type is not None
                    ],
                ),
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
    volume_result = await db.execute(
        select(Message.created_at)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            active_conversation,
            active_message,
            Message.role == MessageRole.user,
            Message.created_at >= window_started_at,
        )
    )
    volume_counts: dict[tuple[str, int], int] = {}
    for created_at in volume_result.scalars().all():
        key = (created_at.date().isoformat(), created_at.hour)
        volume_counts[key] = volume_counts.get(key, 0) + 1
    first_day = generated_at.date() - timedelta(days=6)
    message_volume = [
        AdminMessageVolumePoint(
            date=(first_day + timedelta(days=day_offset)).isoformat(),
            hour=hour,
            count=volume_counts.get(
                ((first_day + timedelta(days=day_offset)).isoformat(), hour), 0
            ),
        )
        for day_offset in range(7)
        for hour in range(24)
    ]
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
        message_volume=message_volume,
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
    coordinator: ChatRunCoordinatorDep,
    request_id: RequestIDDep,
):
    started = await _start_durable_chat_run(
        coordinator=coordinator,
        conversation_id=conversation_id,
        content=payload.content,
        db=db,
        user=user,
        request_id=request_id,
    )
    await asyncio.shield(started.task)

    hydrated_stmt = (
        select(Message)
        .where(Message.id == started.assistant_message_id)
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
    coordinator: ChatRunCoordinatorDep,
    request_id: RequestIDDep,
):
    started = await _start_durable_chat_run(
        coordinator=coordinator,
        conversation_id=conversation_id,
        content=payload.content,
        db=db,
        user=user,
        request_id=request_id,
    )

    async def event_generator() -> AsyncIterator[str]:
        yield sse_event(
            {
                "type": "run_accepted",
                "run_id": started.run_id,
                "user_message_id": started.user_message_id,
                "assistant_message_id": started.assistant_message_id,
            }
        )
        async for event in started.subscription.events():
            yield sse_event(event)

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
