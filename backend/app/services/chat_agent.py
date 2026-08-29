"""Conversation-facing application service for the NetAI Agent."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import asdict, dataclass
from enum import Enum
from time import perf_counter
from uuid import uuid4

from haystack.dataclasses import ChatMessage
from haystack.tools import Tool

from app.prompts import FORMATTING_PROMPT
from app.services.agent_events import RunObserver
from app.services.chat_attachments import (
    load_active_attachments_for_prompt,
    render_attachment_reference_text,
)
from app.services.conversation_context import (
    BuiltContext,
    build_conversation_context,
    estimate_tokens,
)
from app.services.netai import NetAIService

SkillInstruction = dict[str, str]


@dataclass(slots=True)
class PromptSnapshotMessage:
    index: int
    role: str
    source: str
    text: str
    estimated_tokens: int
    message_id: int | None = None
    summary_id: int | None = None
    up_to_message_id: int | None = None


@dataclass(slots=True)
class AgentPromptSnapshot:
    messages: list[PromptSnapshotMessage]
    metrics: dict[str, object]


@dataclass(slots=True)
class PreparedAgentPrompt:
    messages: list[ChatMessage]
    message_sources: list[dict[str, int | str | None]]
    context: BuiltContext
    attachment_reference_text: str
    metrics: dict[str, object]
    snapshot: AgentPromptSnapshot


def _message_role(message: ChatMessage) -> str:
    role = message.role
    return str(role.value if isinstance(role, Enum) else role).lower()


def _runtime_message_source(
    message: ChatMessage, *, is_first: bool, is_last: bool
) -> str:
    role = _message_role(message)
    if message.tool_calls:
        return "assistant_tool_call"
    if message.tool_call_results:
        return "tool_result"
    if role == "system":
        return "agent_system_prompt" if is_first else "runtime_system"
    if role == "assistant" and is_last:
        return "assistant_response"
    return f"runtime_{role}"


def _runtime_message_text(message: ChatMessage) -> str:
    sections: list[str] = []
    if message.text:
        sections.append(message.text)
    if message.tool_calls:
        sections.append(
            "Tool calls:\n"
            + json.dumps(
                [call.to_dict() for call in message.tool_calls],
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    if message.tool_call_results:
        sections.append(
            "Tool results:\n"
            + json.dumps(
                [result.to_dict() for result in message.tool_call_results],
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    return "\n\n".join(sections)


def build_runtime_prompt_snapshot(
    *,
    result: dict[str, object],
    metrics: dict[str, object],
) -> AgentPromptSnapshot:
    """Capture the completed Agent trace used by the message debug panel."""

    raw_messages = result.get("messages")
    messages = (
        [message for message in raw_messages if isinstance(message, ChatMessage)]
        if isinstance(raw_messages, list)
        else []
    )
    snapshot_messages: list[PromptSnapshotMessage] = []
    last_index = len(messages) - 1
    for index, message in enumerate(messages):
        text = _runtime_message_text(message)
        snapshot_messages.append(
            PromptSnapshotMessage(
                index=index,
                role=_message_role(message),
                source=_runtime_message_source(
                    message,
                    is_first=index == 0,
                    is_last=index == last_index,
                ),
                text=text,
                estimated_tokens=max(1, len(text) // 4),
            )
        )
    return AgentPromptSnapshot(
        messages=snapshot_messages,
        metrics=dict(metrics),
    )


def _build_skills_prompt(skills: list[SkillInstruction] | None) -> str:
    if not skills:
        return ""
    sections = [
        "User-selected skills explicitly invoked for this request:",
        "Apply them unless they conflict with safety or factual correctness.",
    ]
    for index, skill in enumerate(skills, start=1):
        instructions = str(skill.get("instructions") or "").strip()
        if not instructions:
            continue
        name = str(skill.get("name") or f"Skill {index}").strip()
        sections.extend((f"{index}. {name}", instructions))
    return "\n".join(sections).strip()


def _custom_instructions_prompt(custom_instructions: str | None) -> str:
    normalized = str(custom_instructions or "").strip()
    if not normalized:
        return ""
    return (
        "Custom instructions from the user. Apply them unless they conflict with "
        f"safety or factual accuracy:\n\n{normalized}"
    )


def _insert_before_latest_user(
    messages: list[ChatMessage],
    sources: list[dict[str, int | str | None]],
    message: ChatMessage,
    source: str,
) -> None:
    insertion_index = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        if _message_role(messages[index]) == "user":
            insertion_index = index
            break
    messages.insert(insertion_index, message)
    sources.insert(insertion_index, {"source": source})


def _replace_latest_user(
    messages: list[ChatMessage],
    sources: list[dict[str, int | str | None]],
    question: str,
) -> None:
    for index in range(len(messages) - 1, -1, -1):
        if _message_role(messages[index]) == "user":
            messages[index] = ChatMessage.from_user(question)
            del messages[index + 1 :]
            del sources[index + 1 :]
            return
    messages.append(ChatMessage.from_user(question))
    sources.append({"source": "current_question"})


def _source_int(source: dict[str, int | str | None], key: str) -> int | None:
    value = source.get(key)
    return value if isinstance(value, int) else None


def _tool_context(tools: Iterable[Tool]) -> str:
    return "\n\n".join(
        f"name: {tool.name}\ndescription: {tool.description}\n"
        f"parameters: {json.dumps(tool.parameters, sort_keys=True)}"
        for tool in tools
    )


def _context_metrics(
    *,
    service: NetAIService,
    context: BuiltContext,
    messages: list[ChatMessage],
    attachment_reference_text: str,
    tool_context: str,
) -> dict[str, object]:
    breakdown = {
        "system": {
            "tokens": estimate_tokens(
                [ChatMessage.from_system(service.agent.system_prompt or "")]
            )
        },
        "user": {"tokens": 0},
        "assistant": {"tokens": 0},
        "tools": {
            "tokens": max(1, len(tool_context) // 4),
        },
        "documents": {"tokens": 0},
    }
    for message in messages:
        tokens = max(1, len(message.text or "") // 4)
        if attachment_reference_text and message.text == attachment_reference_text:
            breakdown["documents"]["tokens"] += tokens
            continue
        role = _message_role(message)
        bucket = role if role in {"system", "user", "assistant"} else "tools"
        breakdown[bucket]["tokens"] += tokens

    used_tokens = sum(item["tokens"] for item in breakdown.values())
    context_window = context.context_window
    used_percent = (
        int(round((used_tokens / context_window) * 100)) if context_window > 0 else 0
    )
    used_percent = max(0, min(100, used_percent))
    return {
        "context_window": context_window,
        "used_tokens": used_tokens,
        "used_percent": used_percent,
        "left_tokens": max(context_window - used_tokens, 0),
        "left_percent": max(0, min(100, 100 - used_percent)),
        "compacted": context.compacted,
        "summary_id": context.used_summary_id,
        "breakdown": breakdown,
    }


async def prepare_agent_prompt(
    *,
    service: NetAIService,
    conversation_id: str,
    question: str,
    skills: list[SkillInstruction] | None = None,
    custom_instructions: str | None = None,
    include_draft_question: bool = False,
) -> PreparedAgentPrompt:
    context = await build_conversation_context(
        conversation_id=conversation_id,
        generate=service.generate,
        context_window=service.settings.LLM_CONTEXT_WINDOW,
        keep_recent=service.settings.CHAT_CONTEXT_RECENT_MESSAGES,
    )
    attachments = await load_active_attachments_for_prompt(
        conversation_id=conversation_id
    )
    attachment_text = render_attachment_reference_text(attachments)
    messages = list(context.messages)
    sources = [dict(source) for source in context.message_sources]

    if include_draft_question:
        messages.append(ChatMessage.from_user(question))
        sources.append({"source": "current_question"})
    else:
        _replace_latest_user(messages, sources, question)

    if attachment_text:
        _insert_before_latest_user(
            messages,
            sources,
            ChatMessage.from_user(attachment_text),
            "attachments",
        )
    custom_prompt = _custom_instructions_prompt(custom_instructions)
    if custom_prompt:
        _insert_before_latest_user(
            messages,
            sources,
            ChatMessage.from_user(custom_prompt),
            "custom_instructions",
        )

    runtime_system_messages: list[tuple[str, str]] = []
    skills_prompt = _build_skills_prompt(skills)
    if skills_prompt:
        runtime_system_messages.append(("selected_skills", skills_prompt))
    if FORMATTING_PROMPT.strip():
        runtime_system_messages.append(("formatting_prompt", FORMATTING_PROMPT))
    for source, text in reversed(runtime_system_messages):
        messages.insert(0, ChatMessage.from_system(text))
        sources.insert(0, {"source": source})

    visible_tool_context = _tool_context(service.registry.searchable)
    metrics = _context_metrics(
        service=service,
        context=context,
        messages=messages,
        attachment_reference_text=attachment_text,
        tool_context=visible_tool_context,
    )
    snapshot_messages = [
        ChatMessage.from_system(service.agent.system_prompt or ""),
        ChatMessage.from_system(visible_tool_context),
        *messages,
    ]
    snapshot_sources: list[dict[str, int | str | None]] = [
        {"source": "agent_system_prompt"},
        {"source": "available_tools"},
        *sources,
    ]
    snapshot = AgentPromptSnapshot(
        messages=[
            PromptSnapshotMessage(
                index=index,
                role=_message_role(message),
                source=str(snapshot_sources[index].get("source") or "unknown"),
                text=message.text or "",
                estimated_tokens=max(1, len(message.text or "") // 4),
                message_id=_source_int(snapshot_sources[index], "message_id"),
                summary_id=_source_int(snapshot_sources[index], "summary_id"),
                up_to_message_id=_source_int(
                    snapshot_sources[index], "up_to_message_id"
                ),
            )
            for index, message in enumerate(snapshot_messages)
        ],
        metrics=metrics,
    )
    return PreparedAgentPrompt(
        messages=messages,
        message_sources=sources,
        context=context,
        attachment_reference_text=attachment_text,
        metrics=metrics,
        snapshot=snapshot,
    )


async def build_agent_prompt_snapshot(
    *,
    service: NetAIService,
    conversation_id: str,
    question: str,
    skills: list[SkillInstruction] | None = None,
    custom_instructions: str | None = None,
    include_draft_question: bool = True,
) -> AgentPromptSnapshot:
    prepared = await prepare_agent_prompt(
        service=service,
        conversation_id=conversation_id,
        question=question,
        skills=skills,
        custom_instructions=custom_instructions,
        include_draft_question=include_draft_question,
    )
    runtime = await service.prepare_run_context(
        prepared.messages,
        conversation_id=conversation_id,
    )

    runtime_sources = [dict(source) for source in prepared.message_sources]
    if runtime.supplemental_messages:
        insertion_index = max(len(runtime_sources) - 1, 0)
        runtime_sources[insertion_index:insertion_index] = [
            {"source": supplemental.source}
            for supplemental in runtime.supplemental_messages
        ]

    visible_tools = list(runtime.tools)
    visible_tool_context = _tool_context(visible_tools)
    selectable_tools = runtime.tools.get_selectable_tools()
    visible_names = {tool.name for tool in visible_tools}
    searchable_tools = [
        tool for tool in selectable_tools if tool.name not in visible_names
    ]

    snapshot_messages = [
        ChatMessage.from_system(service.agent.system_prompt or ""),
        ChatMessage.from_system(visible_tool_context),
    ]
    snapshot_sources: list[dict[str, int | str | None]] = [
        {"source": "agent_system_prompt"},
        {"source": "available_tools"},
    ]
    if searchable_tools:
        snapshot_messages.append(
            ChatMessage.from_system(_tool_context(searchable_tools))
        )
        snapshot_sources.append({"source": "searchable_tool_catalog"})
    snapshot_messages.extend(runtime.messages)
    snapshot_sources.extend(runtime_sources)

    metrics = _context_metrics(
        service=service,
        context=prepared.context,
        messages=runtime.messages,
        attachment_reference_text=prepared.attachment_reference_text,
        tool_context=visible_tool_context,
    )
    return AgentPromptSnapshot(
        messages=[
            PromptSnapshotMessage(
                index=index,
                role=_message_role(message),
                source=str(snapshot_sources[index].get("source") or "unknown"),
                text=message.text or "",
                estimated_tokens=max(1, len(message.text or "") // 4),
                message_id=_source_int(snapshot_sources[index], "message_id"),
                summary_id=_source_int(snapshot_sources[index], "summary_id"),
                up_to_message_id=_source_int(
                    snapshot_sources[index], "up_to_message_id"
                ),
            )
            for index, message in enumerate(snapshot_messages)
        ],
        metrics=metrics,
    )


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    return text.splitlines(keepends=True) or [text]


async def run_agent(
    *,
    service: NetAIService,
    conversation_id: str,
    question: str,
    user_id: int,
    request_id: str | None = None,
    skills: list[SkillInstruction] | None = None,
    custom_instructions: str | None = None,
) -> dict[str, object]:
    prepared = await prepare_agent_prompt(
        service=service,
        conversation_id=conversation_id,
        question=question,
        skills=skills,
        custom_instructions=custom_instructions,
    )
    run = await service.run(
        messages=prepared.messages,
        conversation_id=conversation_id,
        user_id=user_id,
        request_id=request_id,
    )
    prompt_snapshot = build_runtime_prompt_snapshot(
        result=run.result,
        metrics=prepared.metrics,
    )
    return {
        "answer": run.answer,
        "events": run.observer.events,
        "run_map": run.run_map,
        "context_metrics": prepared.metrics,
        "prompt_snapshot": asdict(prompt_snapshot),
    }


async def run_agent_stream(
    *,
    service: NetAIService,
    conversation_id: str,
    question: str,
    user_id: int,
    request_id: str | None = None,
    skills: list[SkillInstruction] | None = None,
    custom_instructions: str | None = None,
) -> AsyncIterator[dict[str, object]]:
    prepared = await prepare_agent_prompt(
        service=service,
        conversation_id=conversation_id,
        question=question,
        skills=skills,
        custom_instructions=custom_instructions,
    )
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    observer = RunObserver(
        run_id=f"run_{uuid4().hex}",
        conversation_id=conversation_id,
        queue=queue,
    )
    await observer.emit("run_started")
    await observer.emit("context_metrics", prepared.metrics)
    started_at = perf_counter()
    run_task = asyncio.create_task(
        service.run(
            messages=prepared.messages,
            conversation_id=conversation_id,
            user_id=user_id,
            request_id=request_id,
            observer=observer,
            stream=True,
        )
    )
    streamed_text: list[str] = []
    try:
        while not run_task.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            if event.get("type") == "token":
                streamed_text.append(str(event.get("token") or ""))
            yield event
        run = await run_task
    except asyncio.CancelledError:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        raise
    except Exception as exc:
        await observer.emit("run_error", {"error": str(exc)})
        while not queue.empty():
            yield queue.get_nowait()
        yield {
            "type": "run_map",
            "run_id": observer.run_id,
            "run_map": {
                "agent": {
                    "agent_name": "netai",
                    "status": "failed",
                    "duration_ms": max(
                        0, int(round((perf_counter() - started_at) * 1000))
                    ),
                    "error": str(exc),
                },
                "tool_calls": [
                    execution.as_dict() for execution in observer.tool_executions
                ],
            },
            "prompt_snapshot": asdict(prepared.snapshot),
        }
        raise

    emitted_text = "".join(streamed_text).strip()
    final_answer = run.answer.strip()
    if final_answer and not emitted_text.endswith(final_answer):
        if emitted_text:
            yield await observer.emit("token", {"token": "\n\n"})
        for token in _tokenize(run.answer):
            yield await observer.emit("token", {"token": token})
    yield await observer.emit("run_finished", {"duration_ms": run.duration_ms})
    yield {
        "type": "run_map",
        "run_id": observer.run_id,
        "run_map": run.run_map,
        "answer": run.answer,
        "prompt_snapshot": asdict(
            build_runtime_prompt_snapshot(
                result=run.result,
                metrics=prepared.metrics,
            )
        ),
    }
