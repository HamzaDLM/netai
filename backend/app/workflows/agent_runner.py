import asyncio
import json
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from enum import Enum
from time import perf_counter
from typing import Any, AsyncIterator

from haystack.dataclasses import ChatMessage

from app.agents.orchestrator_agent import SPECIALIST_DESCRIPTIONS, orchestrator_agent
from app.prompts import FORMATTING_PROMPT
from app.services.chat_attachments import (
    load_active_attachments_for_prompt,
    render_attachment_reference_text,
)
from app.workflows.context_manager import build_conversation_context
from app.workflows.utils import AgentTraceExtractor

_TRACE_EXTRACTOR = AgentTraceExtractor(specialist_descriptions=SPECIALIST_DESCRIPTIONS)
_STREAM_QUEUE: ContextVar[asyncio.Queue[dict[str, Any]] | None] = ContextVar(
    "_STREAM_QUEUE", default=None
)
_STREAM_LOOP: ContextVar[asyncio.AbstractEventLoop | None] = ContextVar(
    "_STREAM_LOOP", default=None
)

SkillInstruction = dict[str, str]


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _serialized_streaming_callback(chunk: Any) -> None:
    """Top-level callback to stay compatible with Haystack callable serialization."""
    content = getattr(chunk, "content", None)
    if not isinstance(content, str) or not content:
        return

    queue = _STREAM_QUEUE.get()
    loop = _STREAM_LOOP.get()
    if queue is None or loop is None:
        return

    loop.call_soon_threadsafe(
        queue.put_nowait,
        {"type": "token", "token": content},
    )


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value


async def _run_agent(
    messages: list[Any],
    *,
    streaming_callback: Any | None = None,
    run_in_thread: bool = False,
) -> Any:
    try:
        kwargs: dict[str, Any] = {"messages": messages}
        if streaming_callback is not None:
            kwargs["streaming_callback"] = streaming_callback
        if run_in_thread:
            return await asyncio.to_thread(orchestrator_agent.run, **kwargs)
        return await _maybe_await(orchestrator_agent.run(**kwargs))
    except TypeError:
        raise Exception("problem with agent message type")


def _with_runtime_formatting_prompt(messages: list[Any]) -> list[Any]:
    if not FORMATTING_PROMPT.strip():
        return messages
    return [*messages, ChatMessage.from_system(FORMATTING_PROMPT)]


def _build_skills_prompt(skills: list[SkillInstruction] | None) -> str:
    if not skills:
        return ""

    lines: list[str] = [
        "Enabled user skills (custom behavior preferences):",
        "Apply these preferences when relevant, unless they conflict with safety or factual correctness.",
    ]
    for index, skill in enumerate(skills, start=1):
        name = str(skill.get("name") or f"Skill {index}").strip() or f"Skill {index}"
        instructions = str(skill.get("instructions") or "").strip()
        if not instructions:
            continue
        lines.append(f"{index}. {name}")
        lines.append(f"   {instructions}")
    return "\n".join(lines).strip()


def _with_runtime_skill_prompts(
    messages: list[Any], skills: list[SkillInstruction] | None
) -> list[Any]:
    skills_prompt = _build_skills_prompt(skills)
    if not skills_prompt:
        return messages
    return [*messages, ChatMessage.from_system(skills_prompt)]


def _with_runtime_attachment_context(
    messages: list[Any],
    *,
    question: str,
    attachment_reference_text: str,
) -> list[Any]:
    if not attachment_reference_text.strip():
        return messages

    out = list(messages)
    latest_question = (
        out.pop()
        if out and getattr(out[-1], "text", None) == question
        else ChatMessage.from_user(question)
    )
    out.append(ChatMessage.from_user(attachment_reference_text))
    out.append(latest_question)
    return out


def _estimate_runtime_tokens(messages: list[Any]) -> int:
    text = "\n".join(getattr(message, "text", "") or "" for message in messages)
    return _estimate_text_tokens(text)


def _normalize_message_role(message: Any) -> str:
    role = getattr(message, "role", None)
    if isinstance(role, Enum):
        role = role.value
    return str(role or "").strip().lower()


def _serialize_tool_metadata_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    elif hasattr(value, "model_dump"):
        value = value.model_dump()
    elif hasattr(value, "dict"):
        value = value.dict()
    elif hasattr(value, "to_dict"):
        value = value.to_dict()

    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        except TypeError:
            return ""
    return ""


def _tool_context_text() -> str:
    lines: list[str] = []

    for tool in getattr(orchestrator_agent, "tools", []) or []:
        tool_lines: list[str] = []
        for attr in (
            "name",
            "description",
            "parameters",
            "inputs",
            "input_schema",
            "parameters_schema",
            "tool_spec",
        ):
            raw_value = getattr(tool, attr, None)
            value = _serialize_tool_metadata_value(raw_value)
            if value:
                tool_lines.append(f"{attr}: {value}")
        if tool_lines:
            lines.append("\n".join(tool_lines))

    return "\n\n".join(lines).strip()


def _runtime_context_breakdown(
    messages: list[Any], *, attachment_reference_text: str = ""
) -> dict[str, dict[str, int]]:
    system_tokens = _estimate_text_tokens(
        getattr(orchestrator_agent, "system_prompt", "") or ""
    )
    user_tokens = 0
    assistant_tokens = 0
    document_tokens = 0
    tool_tokens = 0

    for message in messages:
        text = getattr(message, "text", "") or ""
        tokens = _estimate_text_tokens(text)
        if tokens <= 0:
            continue

        if attachment_reference_text and text == attachment_reference_text:
            document_tokens += tokens
            continue

        role = _normalize_message_role(message)
        if role == "system":
            system_tokens += tokens
            continue
        if role == "tool":
            tool_tokens += tokens
            continue
        if role == "assistant":
            assistant_tokens += tokens
            continue
        user_tokens += tokens

    return {
        "system": {"tokens": system_tokens},
        "user": {"tokens": user_tokens},
        "assistant": {"tokens": assistant_tokens},
        "tools": {"tokens": tool_tokens},
        "documents": {"tokens": document_tokens},
    }


def _runtime_context_metrics(
    context: Any, messages: list[Any], *, attachment_reference_text: str = ""
) -> dict[str, int | bool | None | dict[str, dict[str, int]]]:
    breakdown = _runtime_context_breakdown(
        messages, attachment_reference_text=attachment_reference_text
    )
    estimated_tokens = sum(item["tokens"] for item in breakdown.values())
    context_window = getattr(context, "context_window", 0) or 0
    used_percent = (
        int(round((estimated_tokens / context_window) * 100))
        if context_window > 0
        else 0
    )
    used_percent = max(0, min(100, used_percent))
    left_tokens = max(context_window - estimated_tokens, 0)
    left_percent = max(0, min(100, 100 - used_percent))

    return {
        "context_window": context_window,
        "used_tokens": estimated_tokens,
        "used_percent": used_percent,
        "left_tokens": left_tokens,
        "left_percent": left_percent,
        "compacted": bool(getattr(context, "compacted", False)),
        "summary_id": getattr(context, "used_summary_id", None),
        "breakdown": breakdown,
    }


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    buf = []
    for ch in text:
        buf.append(ch)
        if ch.isspace():
            tokens.append("".join(buf))
            buf = []
    if buf:
        tokens.append("".join(buf))
    return tokens


async def run_agent(
    *,
    conversation_id: str,
    question: str,
    skills: list[SkillInstruction] | None = None,
) -> dict:
    context = await build_conversation_context(conversation_id=conversation_id)
    attachments = await load_active_attachments_for_prompt(
        conversation_id=conversation_id
    )
    attachment_reference_text = render_attachment_reference_text(attachments)
    messages = _with_runtime_formatting_prompt(
        _with_runtime_skill_prompts(
            _with_runtime_attachment_context(
                context.messages,
                question=question,
                attachment_reference_text=attachment_reference_text,
            ),
            skills,
        )
    )
    runtime_metrics = _runtime_context_metrics(
        context,
        messages,
        attachment_reference_text=attachment_reference_text,
    )

    start = perf_counter()
    result = await _run_agent(messages)
    latency_ms = int((perf_counter() - start) * 1000)

    answer = _TRACE_EXTRACTOR.extract_answer(result)
    run_map = _TRACE_EXTRACTOR.build_run_map(result=result, total_latency_ms=latency_ms)
    events = _TRACE_EXTRACTOR.build_run_events(answer=answer, run_map=run_map)
    return {
        "answer": answer,
        "events": events,
        "run_map": run_map,
        "context_metrics": runtime_metrics,
    }


async def run_agent_stream(
    *,
    conversation_id: str,
    question: str,
    skills: list[SkillInstruction] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    context = await build_conversation_context(conversation_id=conversation_id)
    attachments = await load_active_attachments_for_prompt(
        conversation_id=conversation_id
    )
    attachment_reference_text = render_attachment_reference_text(attachments)
    messages = _with_runtime_formatting_prompt(
        _with_runtime_skill_prompts(
            _with_runtime_attachment_context(
                context.messages,
                question=question,
                attachment_reference_text=attachment_reference_text,
            ),
            skills,
        )
    )
    yield {
        "type": "context_metrics",
        **_runtime_context_metrics(
            context,
            messages,
            attachment_reference_text=attachment_reference_text,
        ),
    }

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    streamed_any_token = False
    stream_queue_token = _STREAM_QUEUE.set(queue)
    stream_loop_token = _STREAM_LOOP.set(loop)

    try:
        start = perf_counter()
        run_task = asyncio.create_task(
            _run_agent(
                messages,
                streaming_callback=_serialized_streaming_callback,
                run_in_thread=True,
            )
        )

        while True:
            if run_task.done() and queue.empty():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            if event.get("type") == "token":
                streamed_any_token = True
            yield event

        result = await run_task
    finally:
        _STREAM_QUEUE.reset(stream_queue_token)
        _STREAM_LOOP.reset(stream_loop_token)

    latency_ms = int((perf_counter() - start) * 1000)
    answer = _TRACE_EXTRACTOR.extract_answer(result)
    run_map = _TRACE_EXTRACTOR.build_run_map(result=result, total_latency_ms=latency_ms)

    print("FINAL ANSWER RUN MAP:", run_map)

    if not streamed_any_token:
        for token in _tokenize(answer):
            yield {"type": "token", "token": token}

    for event in _TRACE_EXTRACTOR.build_run_events(answer=answer, run_map=run_map):
        yield event

    # Persistence metadata consumed by API endpoint; not forwarded to client.
    yield {"type": "run_map", "run_map": run_map, "answer": answer}
