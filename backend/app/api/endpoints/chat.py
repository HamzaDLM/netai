import asyncio
import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from haystack.dataclasses import ChatMessage
from app.api.deps import AsyncSessionDep, CheckUserSSODep
from app.api.models.chat import (
    Conversation,
    Evidence,
    Feedback,
    Message,
    ToolCall,
)
from app.api.schemas.chat import (
    ConversationCreate,
    ConversationResponse,
    ConversationMessagesResponse,
    FeedbackCreate,
    MessageCreate,
    MessageResponse,
)
from app.workflows.agent_runner import run_agent, run_agent_stream
from backend.app.llm import llm
from app.db.session import SessionLocal
from app.observability import langfuse_client
from app.prompts import TITLE_GENERATION_PROMPT

router = APIRouter(prefix="/llm", tags=["chat"])


def _derive_tool_source(tool_name: str | None) -> str | None:
    if not tool_name:
        return None
    name = tool_name.strip()
    if not name:
        return None
    if "." in name:
        prefix = name.split(".", 1)[0].strip().lower()
        return prefix or None
    return None


def _normalize_evidence_entries(tool: dict) -> list[dict]:
    evidence = tool.get("evidence") or []
    if evidence:
        return evidence

    result = tool.get("result")
    if result is None:
        return []

    snippet = json.dumps(result, ensure_ascii=True, default=str)
    if len(snippet) > 1500:
        snippet = snippet[:1500] + "...(truncated)"

    tool_name = tool.get("name")
    tool_source = _derive_tool_source(tool_name)
    source_type = tool_source or "tool_result"

    return [
        {
            "type": source_type,
            "ref": tool_name,
            "content": snippet,
            "score": None,
        }
    ]


async def _generate_title_if_missing(
    conversation_id: int,
    user_question: str,
    assistant_content: str,
) -> None:
    """Generate a conversation title asynchronously without blocking stream delivery."""
    async with SessionLocal() as title_db:
        stmt = select(Conversation).where(Conversation.id == conversation_id)
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


@router.post("/conversation", response_model=ConversationResponse)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
):
    conversation = Conversation(
        title=payload.title,
        user_id=user.id,
    )

    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return conversation


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(db: AsyncSessionDep):
    stmt = select(Conversation).order_by(Conversation.updated_at.desc())

    result = await db.execute(stmt)

    conversations = result.scalars().all()

    return conversations


@router.get(
    "/conversation/{conversation_id}", response_model=ConversationMessagesResponse
)
async def get_conversation(
    conversation_id: int,
    db: AsyncSessionDep,
):
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            selectinload(Conversation.messages)
            .selectinload(Message.tool_calls)
            .selectinload(ToolCall.evidence_items)
        )
    )

    result = await db.execute(stmt)

    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return conversation


@router.post("/conversation/{conversation_id}/message", response_model=MessageResponse)
async def ask_llm(
    conversation_id: int,
    payload: MessageCreate,
    db: AsyncSessionDep,
):
    trace = langfuse_client.start_trace(
        "chat.ask_llm",
        session_id=str(conversation_id),
        input={"question": payload.content},
        metadata={"endpoint": "/llm/conversation/{conversation_id}/message"},
    )
    # store user message
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )

    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    agent_span = trace.span("chat.agent_run", input={"question": payload.content})
    try:
        # run agent
        agent_result = await run_agent(
            conversation_id=conversation_id,
            question=payload.content,
        )
        agent_span.end(
            output={
                "tool_calls": len(agent_result.get("tools", [])),
                "context_metrics": agent_result.get("context_metrics"),
            }
        )
    except Exception as exc:
        agent_span.end(output={"error": str(exc)})
        trace.end(output={"error": str(exc)})
        raise

    # store assistant message
    assistant_content = agent_result["answer"]
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

    # store tool_calls + evidence
    for tool in agent_result["tools"]:
        tool_call = ToolCall(
            message_id=assistant_message_id,
            tool_name=tool["name"],
            tool_source=_derive_tool_source(tool.get("name")),
            arguments=tool["arguments"],
            result=tool["result"],
            latency_ms=tool.get("latency_ms"),
        )

        db.add(tool_call)
        await db.flush()

        for ev in _normalize_evidence_entries(tool):
            evidence = Evidence(
                tool_call_id=tool_call.id,
                source_type=ev.get("type", "tool_result"),
                source_ref=ev.get("ref"),
                content_snippet=str(ev.get("content", "")),
                score=ev.get("score"),
            )

            db.add(evidence)

    db_span = trace.span("chat.persist_assistant_message")
    await db.commit()
    db_span.end(
        output={
            "assistant_message_id": assistant_message_id,
            "tool_calls": len(agent_result.get("tools", [])),
        }
    )
    await _generate_title_if_missing(
        conversation_id=conversation_id,
        user_question=payload.content,
        assistant_content=assistant_content,
    )

    hydrated_stmt = (
        select(Message)
        .where(Message.id == assistant_message_id)
        .options(selectinload(Message.tool_calls).selectinload(ToolCall.evidence_items))
    )
    hydrated_result = await db.execute(hydrated_stmt)
    hydrated_message = hydrated_result.scalar_one_or_none()
    if hydrated_message:
        trace.end(
            output={
                "assistant_message_id": assistant_message_id,
                "tool_calls": len(hydrated_message.tool_calls or []),
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
    conversation_id: int,
    payload: MessageCreate,
    db: AsyncSessionDep,
):
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
    await db.commit()

    async def event_generator():
        assistant_tokens: list[str] = []
        tools_called = []
        context_metrics: dict | None = None
        stream_span = trace.span("chat.stream_agent_run")

        try:
            async for event in run_agent_stream(
                conversation_id=conversation_id,
                question=payload.content,
            ):
                if event["type"] == "token":
                    token = event["token"]
                    assistant_tokens.append(token)

                    yield f"event: assistant_token\ndata: {json.dumps({'token': token})}\n\n"
                elif event["type"] == "context_metrics":
                    context_metrics = event
                    yield f"event: context_metrics\ndata: {json.dumps(event)}\n\n"

                elif event["type"] == "tool_call":
                    tools_called.append(event)

                    yield f"event: tool_call\ndata: {json.dumps(event)}\n\n"

                elif event["type"] == "tool_result":
                    yield f"event: tool_result\ndata: {json.dumps(event)}\n\n"
        except Exception as exc:
            stream_span.end(output={"error": str(exc)})
            trace.end(output={"error": str(exc)})
            raise

        assistant_content = "".join(assistant_tokens)

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

        for tool in tools_called:
            tool_call = ToolCall(
                message_id=assistant_message_id,
                tool_name=tool["name"],
                tool_source=_derive_tool_source(tool.get("name")),
                arguments=tool["arguments"],
                result=tool.get("result"),
            )

            db.add(tool_call)
            await db.flush()

            for ev in _normalize_evidence_entries(tool):
                evidence = Evidence(
                    tool_call_id=tool_call.id,
                    source_type=ev.get("type", "tool_result"),
                    source_ref=ev.get("ref"),
                    content_snippet=str(ev.get("content", "")),
                    score=ev.get("score"),
                )
                db.add(evidence)

        await db.commit()
        stream_span.end(
            output={
                "assistant_message_id": assistant_message_id,
                "token_count_chars": len(assistant_content),
                "tool_calls": len(tools_called),
                "context_metrics": context_metrics,
            }
        )
        trace.end(
            output={
                "assistant_message_id": assistant_message_id,
                "tool_calls": len(tools_called),
                "context_metrics": context_metrics,
            }
        )

        yield f"event: done\ndata: {json.dumps({'message_id': assistant_message_id})}\n\n"

        # Run title generation after the client already received "done",
        # so it cannot interfere with token/tool streaming latency.
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


@router.get("/tool_call/{tool_call_id}")
async def get_tool_call(
    tool_call_id: int,
    db: AsyncSessionDep,
):
    stmt = (
        select(ToolCall)
        .where(ToolCall.id == tool_call_id)
        .options(selectinload(ToolCall.evidence_items))
    )

    result = await db.execute(stmt)

    tool_call = result.scalar_one_or_none()

    if not tool_call:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return tool_call


@router.post("/messages/{message_id}/feedback")
async def submit_feedback(
    message_id: int,
    payload: FeedbackCreate,
    db: AsyncSessionDep,
):
    feedback = Feedback(
        message_id=message_id,
        user_id=1,
        rating=payload.rating,
        comment=payload.comment,
    )

    db.add(feedback)

    await db.commit()


@router.patch("/conversation/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: int,
    payload: ConversationCreate,
    db: AsyncSessionDep,
):
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    conversation.title = payload.title

    await db.commit()
    await db.refresh(conversation)

    return conversation


# TODO mark as delete instead of deleting, and use in UI
@router.delete(
    "/conversation/mark/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def mark_deleted_conversation(
    conversation_id: int,
    db: AsyncSessionDep,
):
    raise NotImplementedError


@router.delete(
    "/conversation/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    conversation_id: int,
    db: AsyncSessionDep,
):
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await db.delete(conversation)
    await db.commit()
