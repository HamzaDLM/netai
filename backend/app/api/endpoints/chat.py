import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from haystack.dataclasses import ChatMessage
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import AsyncSessionDep, CheckUserSSODep
from app.api.models.chat import (
    AgentRun,
    AgentRunStatus,
    AgentType,
    Conversation,
    ConversationAttachment,
    Feedback,
    Message,
    MessageRole,
    SubAgentCall,
    ToolCall,
    ToolCallStatus,
)
from app.api.models.skills import Skill
from app.api.schemas.chat import (
    ConversationAttachmentCreate,
    ConversationAttachmentResponse,
    ConversationCreate,
    ConversationMessagesResponse,
    ConversationResponse,
    FeedbackCreate,
    MessageCreate,
    MessageResponse,
)
from app.core.config import project_settings
from app.db.session import SessionLocal
from app.llm import llm
from app.observability import langfuse_client
from app.prompts import TITLE_GENERATION_PROMPT
from app.services.chat_attachments import (
    get_active_attachment_count,
    get_active_attachment_total_chars,
    list_active_attachments,
    parse_attachment_payload,
)
from app.workflows.agent_runner import run_agent, run_agent_stream

router = APIRouter(prefix="/llm", tags=["chat"])


def _event_actor(event: dict[str, Any]) -> tuple[str | None, str | None]:
    event_type = str(event.get("type", "")).strip()
    if not event_type:
        return None, None
    if event_type.startswith("specialist_"):
        return "specialist", str(event.get("specialist") or "unknown")
    if event_type in {
        "orchestrator_decision",
        "orchestrator_plan",
        "leader_conclusion",
    }:
        return "orchestrator", "orchestrator"
    if event_type == "thinking":
        agent = str(event.get("agent") or "orchestrator")
        return (
            ("orchestrator", agent)
            if agent == "orchestrator"
            else ("specialist", agent)
        )
    if event_type in {"tool_call", "tool_result"}:
        return "tool", str(event.get("name") or "unknown_tool")
    return "system", event_type


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


def _message_load_options():
    return [
        selectinload(Message.agent_runs).selectinload(AgentRun.sub_agent_calls),
        selectinload(Message.agent_runs).selectinload(AgentRun.tool_calls),
        selectinload(Message.agent_runs)
        .selectinload(AgentRun.child_runs)
        .selectinload(AgentRun.tool_calls),
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


async def _load_enabled_skills(
    *,
    db: AsyncSessionDep,
    user_id: int,
) -> list[dict[str, str]]:
    stmt = (
        select(Skill)
        .where(
            Skill.user_id == user_id,
            Skill.archived.is_(False),
            Skill.enabled.is_(True),
        )
        .order_by(Skill.created_at.asc())
    )
    result = await db.execute(stmt)
    skills = result.scalars().all()
    return [
        {
            "name": str(skill.name or "").strip(),
            "instructions": str(skill.instructions or "").strip(),
        }
        for skill in skills
        if str(skill.instructions or "").strip()
    ]


async def _persist_run_graph(
    *,
    db: AsyncSessionDep,
    conversation_id: str,
    user_message_id: int,
    assistant_message_id: int,
    assistant_content: str,
    context_metrics: dict[str, Any] | None,
    run_map: dict[str, Any] | None,
) -> AgentRun:
    orchestrator_map = run_map.get("orchestrator") if isinstance(run_map, dict) else {}
    if not isinstance(orchestrator_map, dict):
        orchestrator_map = {}
    sub_agent_calls = (
        run_map.get("sub_agent_calls") if isinstance(run_map, dict) else []
    )
    if not isinstance(sub_agent_calls, list):
        sub_agent_calls = []

    orchestrator_status = _as_run_status(orchestrator_map.get("status"))
    orchestrator_started, orchestrator_ended = _derive_times(
        orchestrator_map.get("duration_ms")
    )
    orchestrator_run = AgentRun(
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        parent_run_id=None,
        agent_type=AgentType.orchestrator,
        agent_name=str(orchestrator_map.get("agent_name") or "orchestrator"),
        depth=0,
        status=orchestrator_status,
        started_at=orchestrator_started,
        ended_at=orchestrator_ended,
        duration_ms=orchestrator_map.get("duration_ms")
        if isinstance(orchestrator_map.get("duration_ms"), int)
        else None,
        final_answer=assistant_content,
        context_metrics=context_metrics,
        error=str(orchestrator_map.get("error"))
        if orchestrator_status == AgentRunStatus.failed
        and orchestrator_map.get("error") is not None
        else None,
    )
    db.add(orchestrator_run)
    await db.flush()

    for index, sub_call in enumerate(sub_agent_calls, start=1):
        if not isinstance(sub_call, dict):
            continue
        specialist_name = str(sub_call.get("specialist_name") or "unknown")
        specialist_status = _as_run_status(sub_call.get("status"))
        specialist_started, specialist_ended = _derive_times(
            sub_call.get("duration_ms")
        )
        specialist_run = AgentRun(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=None,
            parent_run_id=orchestrator_run.id,
            agent_type=AgentType.specialist,
            agent_name=specialist_name,
            depth=1,
            status=specialist_status,
            started_at=specialist_started,
            ended_at=specialist_ended,
            duration_ms=sub_call.get("duration_ms")
            if isinstance(sub_call.get("duration_ms"), int)
            else None,
            final_answer=str(sub_call.get("result_summary"))
            if sub_call.get("result_summary") is not None
            else None,
            context_metrics=None,
            error=str(sub_call.get("error_message"))
            if specialist_status == AgentRunStatus.failed
            and sub_call.get("error_message") is not None
            else None,
        )
        db.add(specialist_run)
        await db.flush()

        db.add(
            SubAgentCall(
                parent_run_id=orchestrator_run.id,
                child_run_id=specialist_run.id,
                specialist_name=specialist_name,
                call_sequence=(
                    sub_call.get("call_sequence")
                    if isinstance(sub_call.get("call_sequence"), int)
                    else index
                ),
                task_prompt=str(sub_call.get("task_prompt") or ""),
                result_summary=str(sub_call.get("result_summary"))
                if sub_call.get("result_summary") is not None
                else None,
                status=_as_tool_status(sub_call.get("status")),
            )
        )

        for tool in sub_call.get("tool_calls") or []:
            if not isinstance(tool, dict):
                continue
            output_payload = _coerce_json_dict(tool.get("output"))
            evidence_payload = tool.get("evidence")
            if isinstance(evidence_payload, list):
                output_payload = {**output_payload, "evidence": evidence_payload}
            db.add(
                ToolCall(
                    run_id=specialist_run.id,
                    conversation_id=conversation_id,
                    tool_name=str(tool.get("tool_name") or "unknown_tool"),
                    input_params=_coerce_json_dict(tool.get("input_params")),
                    output=output_payload,
                    status=_as_tool_status(tool.get("status")),
                    error_type=str(tool.get("error_type"))
                    if tool.get("error_type") is not None
                    else None,
                    error_message=str(tool.get("error_message"))
                    if tool.get("error_message") is not None
                    else None,
                )
            )

    return orchestrator_run


async def _generate_title_if_missing(
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

        trace = langfuse_client.start_trace(
            "chat.generate_title_background",
            session_id=str(conversation_id),
            input={
                "question": user_question,
                "answer_preview": assistant_content[:300],
            },
            metadata={"mode": "stream_background"},
        )
        title_span = trace.generation(
            "chat.generate_title",
            model="gemini_title_generation",
            input={
                "question": user_question,
                "answer_preview": assistant_content[:300],
            },
        )
        try:
            llm_result = await asyncio.to_thread(
                llm.run,
                messages=[
                    ChatMessage.from_system(TITLE_GENERATION_PROMPT),
                    ChatMessage.from_user(
                        f"user question: {user_question} \n LLM assistant answer: {assistant_content}"
                    ),
                ],
            )
            title = llm_result["replies"][0].text.strip()
            if not title:
                title_span.end(output={"skipped": "empty_title"})
                trace.end(output={"skipped": "empty_title"})
                return
            conversation.title = title
            await title_db.commit()
            await title_db.refresh(conversation)
            title_span.end(output={"title": conversation.title})
            trace.end(output={"title": conversation.title})
        except Exception as exc:
            await title_db.rollback()
            title_span.end(output={"error": str(exc)})
            trace.end(output={"error": str(exc)})


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
            .selectinload(AgentRun.child_runs)
            .selectinload(AgentRun.tool_calls),
            selectinload(Conversation.messages).selectinload(Message.feedback),
        )
    )
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return conversation


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    attachment_count = await get_active_attachment_count(
        db, conversation_id=conversation_id
    )
    if attachment_count >= project_settings.CHAT_ATTACHMENT_MAX_COUNT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
):
    await _get_active_conversation(db, conversation_id)

    trace = langfuse_client.start_trace(
        "chat.ask_llm",
        session_id=str(conversation_id),
        input={"question": payload.content},
        metadata={"endpoint": "/llm/conversation/{conversation_id}/message"},
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
    enabled_skills = await _load_enabled_skills(db=db, user_id=user.id)

    agent_span = trace.span("chat.agent_run", input={"question": payload.content})
    try:
        agent_result = await run_agent(
            conversation_id=conversation_id,
            question=payload.content,
            skills=enabled_skills,
        )
        agent_span.end(
            output={
                "events": len(agent_result.get("events", [])),
                "context_metrics": agent_result.get("context_metrics"),
            }
        )
    except Exception as exc:
        agent_span.end(output={"error": str(exc)})
        trace.end(output={"error": str(exc)})
        raise

    assistant_content = agent_result.get("answer") or ""
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        token_input=(
            int(agent_result.get("context_metrics", {}).get("used_tokens", 0))
            if isinstance(agent_result.get("context_metrics"), dict)
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
        context_metrics=agent_result.get("context_metrics")
        if isinstance(agent_result.get("context_metrics"), dict)
        else None,
        run_map=agent_result.get("run_map")
        if isinstance(agent_result.get("run_map"), dict)
        else None,
    )

    db_span = trace.span("chat.persist_assistant_message")
    await db.commit()
    db_span.end(output={"assistant_message_id": assistant_message_id})

    await _generate_title_if_missing(
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
        trace.end(
            output={
                "assistant_message_id": assistant_message_id,
                "agent_runs": len(hydrated_message.agent_runs or []),
                "context_metrics": agent_result.get("context_metrics"),
            }
        )
        return hydrated_message

    trace.end(output={"error": "assistant_message_hydration_failed"})
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="assistant_message_hydration_failed",
    )


@router.post("/conversation/{conversation_id}/message/stream")
async def ask_llm_stream(
    conversation_id: str,
    payload: MessageCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    await _get_active_conversation(db, conversation_id)

    trace = langfuse_client.start_trace(
        "chat.ask_llm_stream",
        session_id=str(conversation_id),
        input={"question": payload.content},
        metadata={"endpoint": "/llm/conversation/{conversation_id}/message/stream"},
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
    enabled_skills = await _load_enabled_skills(db=db, user_id=user.id)

    async def event_generator():
        assistant_tokens: list[str] = []
        context_metrics: dict[str, Any] | None = None
        run_map: dict[str, Any] | None = None
        final_answer: str | None = None
        streamed_event_count = 0
        stream_span = trace.span("chat.stream_agent_run")

        try:
            async for event in run_agent_stream(
                conversation_id=conversation_id,
                question=payload.content,
                skills=enabled_skills,
            ):
                event_type = str(event.get("type") or "")
                if event_type == "token":
                    token = str(event.get("token") or "")
                    assistant_tokens.append(token)
                    yield f"event: assistant_token\ndata: {json.dumps({'token': token})}\n\n"
                    continue
                if event_type == "context_metrics":
                    if isinstance(event, dict):
                        context_metrics = event
                    yield f"event: context_metrics\ndata: {json.dumps(event)}\n\n"
                    continue
                if event_type == "run_map":
                    maybe_map = event.get("run_map")
                    if isinstance(maybe_map, dict):
                        run_map = maybe_map
                    answer_value = event.get("answer")
                    if isinstance(answer_value, str) and answer_value:
                        final_answer = answer_value
                    continue

                if event_type in {
                    "orchestrator_decision",
                    "orchestrator_plan",
                    "specialist_plan",
                    "specialist_prompt",
                    "specialist_tool_call",
                    "specialist_evidence",
                    "specialist_tool_result",
                    "leader_conclusion",
                }:
                    streamed_event_count += 1
                    yield f"event: {event_type}\ndata: {json.dumps(event)}\n\n"
                    continue
        except Exception as exc:
            stream_span.end(output={"error": str(exc)})
            trace.end(output={"error": str(exc)})
            raise

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

        await _persist_run_graph(
            db=db,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            assistant_content=assistant_content,
            context_metrics=context_metrics
            if isinstance(context_metrics, dict)
            else None,
            run_map=run_map,
        )

        await db.commit()
        stream_span.end(
            output={
                "assistant_message_id": assistant_message_id,
                "token_count_chars": len(assistant_content),
                "events": streamed_event_count,
                "context_metrics": context_metrics,
            }
        )
        trace.end(
            output={
                "assistant_message_id": assistant_message_id,
                "events": streamed_event_count,
                "context_metrics": context_metrics,
            }
        )
        yield f"event: done\ndata: {json.dumps({'message_id': assistant_message_id})}\n\n"

        asyncio.create_task(
            _generate_title_if_missing(
                conversation_id=conversation_id,
                user_question=payload.content,
                assistant_content=assistant_content,
            )
        )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
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
