import asyncio
import json

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from haystack.dataclasses import ChatMessage
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AsyncSessionDep, CheckUserSSODep
from app.api.models.chat import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    Conversation,
    Feedback,
    Message,
)
from app.api.schemas.chat import (
    ConversationCreate,
    ConversationMessagesResponse,
    ConversationResponse,
    FeedbackCreate,
    MessageCreate,
    MessageResponse,
)
from app.db.session import SessionLocal
from app.llm import llm
from app.observability import langfuse_client
from app.prompts import TITLE_GENERATION_PROMPT
from app.workflows.agent_runner import run_agent, run_agent_stream

router = APIRouter(prefix="/llm", tags=["chat"])


def _event_actor(event: dict) -> tuple[str | None, str | None]:
    event_type = str(event.get("type", "")).strip()
    if not event_type:
        return None, None
    if event_type.startswith("specialist_"):
        return "specialist", str(event.get("specialist") or "unknown")
    if event_type == "orchestrator_plan":
        return "orchestrator", "orchestrator"
    if event_type == "thinking":
        agent = str(event.get("agent") or "orchestrator")
        actor_type = "orchestrator" if agent == "orchestrator" else "specialist"
        return actor_type, agent
    if event_type in {"tool_call", "tool_result"}:
        return "tool", str(event.get("name") or "unknown_tool")
    if event_type == "leader_conclusion":
        return "orchestrator", "orchestrator"
    return "system", event_type


async def _generate_title_if_missing(
    conversation_id: str,
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
    conversation_id: str,
    db: AsyncSessionDep,
):
    stmt = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(
            selectinload(Conversation.messages)
            .selectinload(Message.agent_runs)
            .selectinload(AgentRun.events)
        )
    )

    result = await db.execute(stmt)

    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return conversation


@router.post("/conversation/{conversation_id}/message", response_model=MessageResponse)
async def ask_llm(
    conversation_id: str,
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
    await db.flush()
    user_message_id = user_message.id
    await db.commit()

    agent_span = trace.span("chat.agent_run", input={"question": payload.content})
    try:
        # run agent
        agent_result = await run_agent(
            conversation_id=conversation_id,
            question=payload.content,
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

    run = AgentRun(
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        status=AgentRunStatus.completed,
        final_answer=assistant_content,
        context_metrics=(
            agent_result.get("context_metrics")
            if isinstance(agent_result.get("context_metrics"), dict)
            else None
        ),
    )
    db.add(run)
    await db.flush()

    for event_sequence, event in enumerate(agent_result.get("events", []), start=1):
        actor_type, actor_name = _event_actor(event)
        db.add(
            AgentEvent(
                run_id=run.id,
                event_sequence=event_sequence,
                event_type=str(event.get("type") or "unknown"),
                actor_type=actor_type,
                actor_name=actor_name,
                payload=event,
                correlation_id=None,
            )
        )

    db_span = trace.span("chat.persist_assistant_message")
    await db.commit()
    db_span.end(
        output={
            "assistant_message_id": assistant_message_id,
            "events": len(agent_result.get("events", [])),
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
        .options(selectinload(Message.agent_runs).selectinload(AgentRun.events))
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
    await db.flush()
    user_message_id = user_message.id
    await db.commit()

    async def event_generator():
        assistant_tokens: list[str] = []
        run_events: list[dict] = []
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
                elif event["type"] == "thinking":
                    run_events.append(event)
                    yield f"event: thinking\ndata: {json.dumps(event)}\n\n"
                elif event["type"] == "orchestrator_plan":
                    run_events.append(event)
                    yield f"event: orchestrator_plan\ndata: {json.dumps(event)}\n\n"
                elif event["type"] == "specialist_prompt":
                    run_events.append(event)
                    yield f"event: specialist_prompt\ndata: {json.dumps(event)}\n\n"
                elif event["type"] == "specialist_thought":
                    run_events.append(event)
                    yield f"event: specialist_thought\ndata: {json.dumps(event)}\n\n"
                elif event["type"] == "specialist_tool_call":
                    run_events.append(event)
                    yield f"event: specialist_tool_call\ndata: {json.dumps(event)}\n\n"
                elif event["type"] == "specialist_tool_result":
                    run_events.append(event)
                    yield f"event: specialist_tool_result\ndata: {json.dumps(event)}\n\n"
                elif event["type"] == "leader_conclusion":
                    run_events.append(event)
                    yield f"event: leader_conclusion\ndata: {json.dumps(event)}\n\n"
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

        run = AgentRun(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            status=AgentRunStatus.completed,
            final_answer=assistant_content,
            context_metrics=context_metrics
            if isinstance(context_metrics, dict)
            else None,
        )
        db.add(run)
        await db.flush()

        for event_sequence, event in enumerate(run_events, start=1):
            actor_type, actor_name = _event_actor(event)
            db.add(
                AgentEvent(
                    run_id=run.id,
                    event_sequence=event_sequence,
                    event_type=str(event.get("type") or "unknown"),
                    actor_type=actor_type,
                    actor_name=actor_name,
                    payload=event,
                    correlation_id=None,
                )
            )

        await db.commit()
        stream_span.end(
            output={
                "assistant_message_id": assistant_message_id,
                "token_count_chars": len(assistant_content),
                "events": len(run_events),
                "context_metrics": context_metrics,
            }
        )
        trace.end(
            output={
                "assistant_message_id": assistant_message_id,
                "events": len(run_events),
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
    conversation_id: str,
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
    conversation_id: str,
    db: AsyncSessionDep,
):
    raise NotImplementedError


@router.delete(
    "/conversation/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSessionDep,
):
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await db.delete(conversation)
    await db.commit()
