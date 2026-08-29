"""Application-owned execution and persistence for durable chat agent runs."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from haystack.dataclasses import ChatMessage
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.chat import (
    AgentEvent,
    AgentRun,
    AgentRunStatus,
    AgentType,
    Conversation,
    Message,
    MessageRole,
    ToolCall,
    ToolCallStatus,
)
from app.prompts import TITLE_GENERATION_PROMPT
from app.services.chat_agent import run_agent_stream
from app.services.netai import NetAIService

logger = logging.getLogger(__name__)

FAILED_RESPONSE = (
    "Something went wrong while processing this request. Please try again."
)
TIMED_OUT_RESPONSE = (
    "The investigation exceeded its time limit. Please retry or narrow the request."
)
INTERRUPTED_RESPONSE = "The investigation was interrupted while the service was restarting. Please try again."

_ARTIFACT_EVENT_TYPES = {"artifact_snapshot", "artifact_delta"}
_TOOL_EVENT_TYPES = {"tool_started", "tool_completed", "tool_failed"}
_DURABLE_EVENT_TYPES = _ARTIFACT_EVENT_TYPES | _TOOL_EVENT_TYPES | {"run_error"}
_STREAMED_EVENT_TYPES = _DURABLE_EVENT_TYPES | {"run_started", "run_finished"}
_EVENT_ENVELOPE_KEYS = {
    "type",
    "event_id",
    "event_sequence",
    "run_id",
    "conversation_id",
    "emitted_at",
}


class ActiveConversationRunError(RuntimeError):
    """Raised when a conversation already owns a running root agent run."""

    def __init__(self, run_id: int) -> None:
        super().__init__(f"conversation already has active run {run_id}")
        self.run_id = run_id


@dataclass(frozen=True, slots=True)
class ChatRunRequest:
    conversation_id: str
    raw_question: str
    agent_question: str
    user_id: int
    request_id: str
    skills: list[dict[str, str]] | None = None
    custom_instructions: str | None = None


@dataclass(slots=True)
class ChatRunSubscription:
    queue: asyncio.Queue[dict[str, object] | None] = field(
        default_factory=asyncio.Queue
    )
    connected: bool = True

    async def events(self) -> AsyncGenerator[dict[str, object], None]:
        try:
            while True:
                event = await self.queue.get()
                if event is None:
                    return
                yield event
        finally:
            self.connected = False

    def publish(self, event: dict[str, object]) -> None:
        if self.connected:
            self.queue.put_nowait(event)

    def finish(self) -> None:
        if self.connected:
            self.queue.put_nowait(None)


@dataclass(slots=True)
class StartedChatRun:
    run_id: int
    user_message_id: int
    assistant_message_id: int
    subscription: ChatRunSubscription
    task: asyncio.Task[None]


def _event_actor(event: dict[str, Any]) -> tuple[str | None, str | None]:
    event_type = str(event.get("type") or "")
    if event_type in _TOOL_EVENT_TYPES:
        return "tool", str(event.get("tool_name") or "unknown_tool")
    if event_type in _ARTIFACT_EVENT_TYPES:
        artifact = event.get("artifact")
        artifact_kind = artifact.get("kind") if isinstance(artifact, dict) else None
        return "tool", str(event.get("kind") or artifact_kind or "artifact")
    return "system", event_type or None


def _event_correlation_id(event: dict[str, Any]) -> str | None:
    for key in ("artifact_id", "tool_call_id"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    artifact = event.get("artifact")
    if isinstance(artifact, dict):
        value = artifact.get("id")
        if isinstance(value, str) and value:
            return value
    value = event.get("event_id")
    return value if isinstance(value, str) and value else None


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in event.items() if key not in _EVENT_ENVELOPE_KEYS
    }


def _tool_status(value: object) -> ToolCallStatus:
    normalized = str(value or "success").strip().lower()
    if normalized in {"timeout", "timed_out"}:
        return ToolCallStatus.timeout
    if normalized in {"blocked", "requires_approval"}:
        return ToolCallStatus.blocked
    if normalized in {"error", "failed", "failure"}:
        return ToolCallStatus.error
    if normalized == "running":
        return ToolCallStatus.running
    return ToolCallStatus.success


def _json_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"value": value}


class ChatRunCoordinator:
    """Run agents independently of HTTP streams and persist terminal state."""

    def __init__(
        self,
        *,
        service: NetAIService,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.service = service
        self.session_factory = session_factory
        self._tasks: dict[int, asyncio.Task[None]] = {}

    async def recover_interrupted_runs(self) -> None:
        """Release expired runs left behind by a previous process termination."""

        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(
            seconds=self.service.settings.AGENT_RUN_TIMEOUT_SECONDS
        )
        async with self.session_factory() as db:
            running = list(
                (
                    await db.execute(
                        select(AgentRun).where(
                            AgentRun.status == AgentRunStatus.running,
                            AgentRun.parent_run_id.is_(None),
                            AgentRun.started_at <= stale_before,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for run in running:
                run.status = AgentRunStatus.failed
                run.ended_at = now
                run.error = "service_restarted"
                run.final_answer = INTERRUPTED_RESPONSE
                if run.assistant_message_id is not None:
                    assistant = await db.get(Message, run.assistant_message_id)
                    if assistant is not None:
                        assistant.content = INTERRUPTED_RESPONSE
            if running:
                await db.commit()
                logger.warning("recovered %d expired agent run(s)", len(running))

    async def start(self, request: ChatRunRequest) -> StartedChatRun:
        async with self.session_factory() as db:
            conversation = (
                await db.execute(
                    select(Conversation)
                    .where(
                        Conversation.id == request.conversation_id,
                        Conversation.archived.is_(False),
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if conversation is None:
                raise LookupError("conversation_not_found")

            active_run = (
                await db.execute(
                    select(AgentRun)
                    .where(
                        AgentRun.conversation_id == request.conversation_id,
                        AgentRun.parent_run_id.is_(None),
                        AgentRun.status == AgentRunStatus.running,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if active_run is not None:
                started_at = active_run.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                stale_before = datetime.now(timezone.utc) - timedelta(
                    seconds=self.service.settings.AGENT_RUN_TIMEOUT_SECONDS
                )
                if started_at > stale_before:
                    raise ActiveConversationRunError(active_run.id)
                active_run.status = AgentRunStatus.failed
                active_run.ended_at = datetime.now(timezone.utc)
                active_run.error = "expired_agent_run"
                active_run.final_answer = INTERRUPTED_RESPONSE
                if active_run.assistant_message_id is not None:
                    stale_assistant = await db.get(
                        Message, active_run.assistant_message_id
                    )
                    if stale_assistant is not None:
                        stale_assistant.content = INTERRUPTED_RESPONSE
                await db.flush()

            user_message = Message(
                conversation_id=request.conversation_id,
                role=MessageRole.user,
                content=request.raw_question,
            )
            assistant_message = Message(
                conversation_id=request.conversation_id,
                role=MessageRole.assistant,
                content="",
            )
            db.add_all((user_message, assistant_message))
            await db.flush()
            agent_run = AgentRun(
                conversation_id=request.conversation_id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                parent_run_id=None,
                agent_type=AgentType.orchestrator,
                agent_name="netai",
                depth=0,
                status=AgentRunStatus.running,
                started_at=datetime.now(timezone.utc),
            )
            db.add(agent_run)
            try:
                await db.flush()
            except IntegrityError as exc:
                await db.rollback()
                async with self.session_factory() as lookup_db:
                    conflicting_run = (
                        await lookup_db.execute(
                            select(AgentRun.id)
                            .where(
                                AgentRun.conversation_id == request.conversation_id,
                                AgentRun.parent_run_id.is_(None),
                                AgentRun.status == AgentRunStatus.running,
                            )
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                if conflicting_run is not None:
                    raise ActiveConversationRunError(conflicting_run) from exc
                raise
            run_id = agent_run.id
            user_message_id = user_message.id
            assistant_message_id = assistant_message.id
            await db.commit()

        subscription = ChatRunSubscription()
        task = asyncio.create_task(
            self._execute(
                run_id=run_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                request=request,
                subscription=subscription,
            ),
            name=f"chat-run:{run_id}",
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(run_id, None))
        return StartedChatRun(
            run_id=run_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            subscription=subscription,
            task=task,
        )

    async def _execute(
        self,
        *,
        run_id: int,
        user_message_id: int,
        assistant_message_id: int,
        request: ChatRunRequest,
        subscription: ChatRunSubscription,
    ) -> None:
        started_at = perf_counter()
        assistant_tokens: list[str] = []
        assistant_char_count = 0
        context_metrics: dict[str, Any] | None = None
        run_map: dict[str, Any] | None = None
        prompt_snapshot: dict[str, Any] | None = None
        final_answer: str | None = None
        durable_events: list[dict[str, Any]] = []
        error_was_streamed = False
        kwargs: dict[str, Any] = {
            "service": self.service,
            "conversation_id": request.conversation_id,
            "question": request.agent_question,
            "user_id": request.user_id,
            "request_id": request.request_id,
            "skills": request.skills,
        }
        if request.custom_instructions:
            kwargs["custom_instructions"] = request.custom_instructions

        try:
            async for event in run_agent_stream(**kwargs):
                event_type = str(event.get("type") or "")
                if event_type == "token":
                    token = str(event.get("token") or "")
                    assistant_tokens.append(token)
                    assistant_char_count += len(token)
                    subscription.publish({"type": "assistant_token", "token": token})
                    continue
                if event_type == "context_metrics":
                    context_metrics = dict(event)
                    subscription.publish(dict(event))
                    continue
                if event_type == "run_map":
                    value = event.get("run_map")
                    if isinstance(value, dict):
                        run_map = value
                    value = event.get("prompt_snapshot")
                    if isinstance(value, dict):
                        prompt_snapshot = value
                    value = event.get("answer")
                    if isinstance(value, str) and value:
                        final_answer = value
                    continue
                if event_type in _STREAMED_EVENT_TYPES:
                    client_event = {**event, "assistant_offset": assistant_char_count}
                    if event_type in _DURABLE_EVENT_TYPES:
                        durable_events.append(client_event)
                    if event_type == "run_error":
                        error_was_streamed = True
                    subscription.publish(client_event)

            assistant_content = "".join(assistant_tokens).strip()
            if not assistant_content and final_answer:
                assistant_content = final_answer
            duration_ms = self._duration_ms(started_at, run_map)
            await self._persist_terminal_run(
                run_id=run_id,
                assistant_message_id=assistant_message_id,
                conversation_id=request.conversation_id,
                assistant_content=assistant_content,
                context_metrics=context_metrics,
                prompt_snapshot=prompt_snapshot,
                run_map=run_map,
                durable_events=durable_events,
                status=AgentRunStatus.completed,
                duration_ms=duration_ms,
                error=None,
            )
            subscription.publish(
                {
                    "type": "done",
                    "message_id": assistant_message_id,
                    "run_id": run_id,
                    "duration_ms": duration_ms,
                    "status": "completed",
                }
            )
            await self._generate_title_if_missing(
                conversation_id=request.conversation_id,
                user_question=request.raw_question,
                assistant_content=assistant_content,
            )
        except asyncio.CancelledError:
            await self._persist_failure(
                run_id=run_id,
                assistant_message_id=assistant_message_id,
                conversation_id=request.conversation_id,
                response=INTERRUPTED_RESPONSE,
                error="run_cancelled_by_service",
                context_metrics=context_metrics,
                prompt_snapshot=prompt_snapshot,
                run_map=run_map,
                durable_events=durable_events,
                duration_ms=max(0, int((perf_counter() - started_at) * 1000)),
            )
            raise
        except Exception as exc:
            timed_out = isinstance(exc, TimeoutError)
            response = TIMED_OUT_RESPONSE if timed_out else FAILED_RESPONSE
            error = "agent_run_timeout" if timed_out else f"{type(exc).__name__}: {exc}"
            if not error_was_streamed:
                subscription.publish({"type": "run_error", "error": response})
            duration_ms = max(0, int((perf_counter() - started_at) * 1000))
            await self._persist_failure(
                run_id=run_id,
                assistant_message_id=assistant_message_id,
                conversation_id=request.conversation_id,
                response=response,
                error=error,
                context_metrics=context_metrics,
                prompt_snapshot=prompt_snapshot,
                run_map=run_map,
                durable_events=durable_events,
                duration_ms=duration_ms,
            )
            subscription.publish(
                {
                    "type": "done",
                    "message_id": assistant_message_id,
                    "run_id": run_id,
                    "duration_ms": duration_ms,
                    "status": "failed",
                }
            )
            logger.exception("chat agent run %d failed", run_id)
        finally:
            subscription.finish()

    @staticmethod
    def _duration_ms(started_at: float, run_map: dict[str, Any] | None) -> int:
        agent = run_map.get("agent") if isinstance(run_map, dict) else None
        value = agent.get("duration_ms") if isinstance(agent, dict) else None
        return (
            value
            if isinstance(value, int)
            else max(0, int((perf_counter() - started_at) * 1000))
        )

    async def _persist_failure(
        self,
        *,
        run_id: int,
        assistant_message_id: int,
        conversation_id: str,
        response: str,
        error: str,
        context_metrics: dict[str, Any] | None,
        prompt_snapshot: dict[str, Any] | None,
        run_map: dict[str, Any] | None,
        durable_events: list[dict[str, Any]],
        duration_ms: int,
    ) -> None:
        await self._persist_terminal_run(
            run_id=run_id,
            assistant_message_id=assistant_message_id,
            conversation_id=conversation_id,
            assistant_content=response,
            context_metrics=context_metrics,
            prompt_snapshot=prompt_snapshot,
            run_map=run_map,
            durable_events=durable_events,
            status=AgentRunStatus.failed,
            duration_ms=duration_ms,
            error=error,
        )

    async def _persist_terminal_run(
        self,
        *,
        run_id: int,
        assistant_message_id: int,
        conversation_id: str,
        assistant_content: str,
        context_metrics: dict[str, Any] | None,
        prompt_snapshot: dict[str, Any] | None,
        run_map: dict[str, Any] | None,
        durable_events: list[dict[str, Any]],
        status: AgentRunStatus,
        duration_ms: int,
        error: str | None,
    ) -> None:
        async with self.session_factory() as db:
            run = await db.get(AgentRun, run_id)
            assistant = await db.get(Message, assistant_message_id)
            if run is None or assistant is None:
                logger.info("chat run %d was removed before completion", run_id)
                return

            assistant.content = assistant_content
            if context_metrics is not None:
                used_tokens = context_metrics.get("used_tokens")
                assistant.token_input = (
                    used_tokens if isinstance(used_tokens, int) else None
                )
            run.status = status
            run.ended_at = datetime.now(timezone.utc)
            run.duration_ms = duration_ms
            run.final_answer = assistant_content
            run.context_metrics = context_metrics
            run.prompt_snapshot = prompt_snapshot
            run.error = error

            agent_map = run_map.get("agent") if isinstance(run_map, dict) else None
            if isinstance(agent_map, dict):
                run.agent_name = str(agent_map.get("agent_name") or "netai")
            tool_calls = (
                run_map.get("tool_calls") if isinstance(run_map, dict) else None
            )
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    db.add(
                        ToolCall(
                            run_id=run_id,
                            conversation_id=conversation_id,
                            tool_name=str(tool_call.get("tool_name") or "unknown_tool"),
                            input_params=_json_dict(tool_call.get("input_params")),
                            output=_json_dict(tool_call.get("output")),
                            latency_ms=(
                                tool_call.get("latency_ms")
                                if isinstance(tool_call.get("latency_ms"), int)
                                else None
                            ),
                            status=_tool_status(tool_call.get("status")),
                            error_type=(
                                str(tool_call.get("error_type"))
                                if tool_call.get("error_type") is not None
                                else None
                            ),
                            error_message=(
                                str(tool_call.get("error_message"))
                                if tool_call.get("error_message") is not None
                                else None
                            ),
                        )
                    )

            for event in durable_events:
                sequence = event.get("event_sequence")
                if not isinstance(sequence, int):
                    continue
                actor_type, actor_name = _event_actor(event)
                db.add(
                    AgentEvent(
                        run_id=run_id,
                        event_sequence=sequence,
                        event_type=str(event.get("type") or "unknown"),
                        actor_type=actor_type,
                        actor_name=actor_name,
                        correlation_id=_event_correlation_id(event),
                        payload=_event_payload(event),
                    )
                )
            await db.commit()

    async def _generate_title_if_missing(
        self,
        *,
        conversation_id: str,
        user_question: str,
        assistant_content: str,
    ) -> None:
        async with self.session_factory() as db:
            conversation = await db.get(Conversation, conversation_id)
            if conversation is None or conversation.archived or conversation.title:
                return
            try:
                result = await self.service.generate(
                    [
                        ChatMessage.from_system(TITLE_GENERATION_PROMPT),
                        ChatMessage.from_user(
                            "user question: "
                            f"{user_question}\nLLM assistant answer: {assistant_content}"
                        ),
                    ]
                )
                replies = result.get("replies")
                reply = replies[0] if isinstance(replies, list) and replies else None
                title = (
                    (reply.text or "").strip() if isinstance(reply, ChatMessage) else ""
                )
                if title:
                    conversation.title = title[:255]
                    await db.commit()
            except Exception:
                await db.rollback()
                logger.warning("conversation title generation failed", exc_info=True)

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


async def mark_run_failed(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: int,
    response: str = FAILED_RESPONSE,
    error: str = "agent_run_failed",
) -> None:
    """Small fallback used when a run cannot be handed to the coordinator."""

    async with session_factory() as db:
        run = await db.get(AgentRun, run_id)
        if run is None:
            return
        run.status = AgentRunStatus.failed
        run.ended_at = datetime.now(timezone.utc)
        run.final_answer = response
        run.error = error
        if run.assistant_message_id is not None:
            await db.execute(
                update(Message)
                .where(Message.id == run.assistant_message_id)
                .values(content=response)
            )
        await db.commit()


def sse_event(event: dict[str, object]) -> str:
    """Serialize one coordinator event using the chat endpoint's SSE contract."""

    event_type = str(event.get("type") or "message")
    payload = {key: value for key, value in event.items() if key != "type"}
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
