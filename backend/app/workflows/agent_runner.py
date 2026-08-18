import asyncio
import json
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from time import perf_counter
from typing import Any, AsyncIterator
from uuid import uuid4

from haystack.dataclasses import ChatMessage

from app.agent_ui import bind_run_event_sink, emit_run_event
from app.agents.orchestrator_agent import SPECIALIST_DESCRIPTIONS, orchestrator_agent
from app.prompts import FORMATTING_PROMPT
from app.services.chat_attachments import (
    load_active_attachments_for_prompt,
    render_attachment_reference_text,
)
from app.workflows.context_manager import build_conversation_context
from app.workflows.utils import AgentTraceExtractor

_TRACE_EXTRACTOR = AgentTraceExtractor(specialist_descriptions=SPECIALIST_DESCRIPTIONS)
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
    metrics: dict[str, Any]


@dataclass(slots=True)
class PreparedAgentPrompt:
    messages: list[Any]
    context: Any
    attachment_reference_text: str
    metrics: dict[str, Any]
    snapshot: AgentPromptSnapshot


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _serialized_streaming_callback(chunk: Any) -> None:
    """Top-level callback to stay compatible with Haystack callable serialization."""
    content = getattr(chunk, "content", None)
    if not isinstance(content, str) or not content:
        return
    emit_run_event("token", {"token": content})


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


def _message_text(message: Any) -> str:
    return str(getattr(message, "text", "") or "")


def _build_skills_prompt(skills: list[SkillInstruction] | None) -> str:
    if not skills:
        return ""

    lines: list[str] = [
        "User-selected skills explicitly invoked for this request:",
        "Apply these instructions for this request unless they conflict with safety or factual correctness.",
    ]
    for index, skill in enumerate(skills, start=1):
        name = str(skill.get("name") or f"Skill {index}").strip() or f"Skill {index}"
        instructions = str(skill.get("instructions") or "").strip()
        if not instructions:
            continue
        lines.append(f"{index}. {name}")
        lines.append(f"   {instructions}")
    return "\n".join(lines).strip()


def _build_custom_instructions_prompt(custom_instructions: str | None) -> str:
    normalized = str(custom_instructions or "").strip()
    if not normalized:
        return ""

    return (
        "Custom instructions from the user:\n"
        "Apply these instructions when answering unless they conflict with safety, "
        "factual accuracy, or higher-priority instructions.\n\n"
        f"{normalized}"
    )


def _source_int(source: dict[str, Any], key: str) -> int | None:
    value = source.get(key)
    return value if isinstance(value, int) else None


def _snapshot_message(
    *,
    index: int,
    message: Any,
    source: dict[str, Any],
) -> PromptSnapshotMessage:
    text = _message_text(message)
    return PromptSnapshotMessage(
        index=index,
        role=_normalize_message_role(message) or str(source.get("role") or "unknown"),
        source=str(source.get("source") or "unknown"),
        text=text,
        estimated_tokens=_estimate_text_tokens(text),
        message_id=_source_int(source, "message_id"),
        summary_id=_source_int(source, "summary_id"),
        up_to_message_id=_source_int(source, "up_to_message_id"),
    )


def _insert_before_latest_question(
    messages: list[Any],
    sources: list[dict[str, Any]],
    *,
    question: str,
    message: Any,
    source: dict[str, Any],
) -> tuple[list[Any], list[dict[str, Any]]]:
    out_messages = list(messages)
    out_sources = list(sources)
    if out_messages and _message_text(out_messages[-1]) == question:
        latest_question = out_messages.pop()
        latest_question_source = (
            out_sources.pop() if out_sources else {"source": "current_question"}
        )
    else:
        latest_question = ChatMessage.from_user(question)
        latest_question_source = {"source": "current_question"}

    out_messages.append(message)
    out_sources.append(source)
    out_messages.append(latest_question)
    out_sources.append(latest_question_source)
    return out_messages, out_sources


def _with_runtime_formatting_prompt_and_sources(
    messages: list[Any], sources: list[dict[str, Any]]
) -> tuple[list[Any], list[dict[str, Any]]]:
    if not FORMATTING_PROMPT.strip():
        return messages, sources
    return [*messages, ChatMessage.from_system(FORMATTING_PROMPT)], [
        *sources,
        {"source": "formatting_prompt"},
    ]


def _with_runtime_skill_prompts_and_sources(
    messages: list[Any],
    sources: list[dict[str, Any]],
    skills: list[SkillInstruction] | None,
) -> tuple[list[Any], list[dict[str, Any]]]:
    skills_prompt = _build_skills_prompt(skills)
    if not skills_prompt:
        return messages, sources
    return [*messages, ChatMessage.from_system(skills_prompt)], [
        *sources,
        {"source": "selected_skills"},
    ]


def _with_runtime_custom_instructions_and_sources(
    messages: list[Any],
    sources: list[dict[str, Any]],
    *,
    question: str,
    custom_instructions: str | None,
) -> tuple[list[Any], list[dict[str, Any]]]:
    custom_prompt = _build_custom_instructions_prompt(custom_instructions)
    if not custom_prompt:
        return messages, sources
    return _insert_before_latest_question(
        messages,
        sources,
        question=question,
        message=ChatMessage.from_user(custom_prompt),
        source={"source": "custom_instructions"},
    )


def _with_runtime_attachment_context_and_sources(
    messages: list[Any],
    sources: list[dict[str, Any]],
    *,
    question: str,
    attachment_reference_text: str,
) -> tuple[list[Any], list[dict[str, Any]]]:
    if not attachment_reference_text.strip():
        return messages, sources
    return _insert_before_latest_question(
        messages,
        sources,
        question=question,
        message=ChatMessage.from_user(attachment_reference_text),
        source={"source": "attachments"},
    )


def _with_draft_question(
    messages: list[Any],
    sources: list[dict[str, Any]],
    *,
    question: str,
) -> tuple[list[Any], list[dict[str, Any]]]:
    return [*messages, ChatMessage.from_user(question)], [
        *sources,
        {"source": "current_question"},
    ]


def _with_runtime_skill_prompts(
    messages: list[Any], skills: list[SkillInstruction] | None
) -> list[Any]:
    skills_prompt = _build_skills_prompt(skills)
    if not skills_prompt:
        return messages
    return [*messages, ChatMessage.from_system(skills_prompt)]


def _with_runtime_custom_instructions(
    messages: list[Any],
    *,
    question: str,
    custom_instructions: str | None,
) -> list[Any]:
    custom_prompt = _build_custom_instructions_prompt(custom_instructions)
    if not custom_prompt:
        return messages

    out = list(messages)
    latest_question = (
        out.pop()
        if out and getattr(out[-1], "text", None) == question
        else ChatMessage.from_user(question)
    )
    out.append(ChatMessage.from_user(custom_prompt))
    out.append(latest_question)
    return out


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


async def prepare_agent_prompt(
    *,
    conversation_id: str,
    question: str,
    skills: list[SkillInstruction] | None = None,
    custom_instructions: str | None = None,
    include_draft_question: bool = False,
) -> PreparedAgentPrompt:
    context = await build_conversation_context(conversation_id=conversation_id)
    attachments = await load_active_attachments_for_prompt(
        conversation_id=conversation_id
    )
    attachment_reference_text = render_attachment_reference_text(attachments)

    messages = list(context.messages)
    sources: list[dict[str, Any]] = [
        dict(source) for source in getattr(context, "message_sources", [])
    ]
    if len(sources) < len(messages):
        sources.extend(
            {"source": "conversation_context"} for _ in messages[len(sources) :]
        )
    elif len(sources) > len(messages):
        sources = sources[: len(messages)]

    if include_draft_question:
        messages, sources = _with_draft_question(
            messages,
            sources,
            question=question,
        )

    messages, sources = _with_runtime_attachment_context_and_sources(
        messages,
        sources,
        question=question,
        attachment_reference_text=attachment_reference_text,
    )
    messages, sources = _with_runtime_custom_instructions_and_sources(
        messages,
        sources,
        question=question,
        custom_instructions=custom_instructions,
    )
    messages, sources = _with_runtime_skill_prompts_and_sources(
        messages,
        sources,
        skills,
    )
    messages, sources = _with_runtime_formatting_prompt_and_sources(messages, sources)

    metrics = _runtime_context_metrics(
        context,
        messages,
        attachment_reference_text=attachment_reference_text,
    )
    snapshot_items = []
    snapshot_sources: list[dict[str, Any]] = []
    orchestrator_system_prompt = str(
        getattr(orchestrator_agent, "system_prompt", "") or ""
    ).strip()
    if orchestrator_system_prompt:
        snapshot_items.append(ChatMessage.from_system(orchestrator_system_prompt))
        snapshot_sources.append({"source": "orchestrator_system_prompt"})

    tool_context = _tool_context_text()
    if tool_context:
        snapshot_items.append(ChatMessage.from_system(tool_context))
        snapshot_sources.append({"source": "available_tools"})

    snapshot_items.extend(messages)
    snapshot_sources.extend(sources)
    snapshot_messages = [
        _snapshot_message(index=index, message=message, source=snapshot_sources[index])
        for index, message in enumerate(snapshot_items)
    ]
    return PreparedAgentPrompt(
        messages=messages,
        context=context,
        attachment_reference_text=attachment_reference_text,
        metrics=metrics,
        snapshot=AgentPromptSnapshot(messages=snapshot_messages, metrics=metrics),
    )


async def build_agent_prompt_snapshot(
    *,
    conversation_id: str,
    question: str,
    skills: list[SkillInstruction] | None = None,
    custom_instructions: str | None = None,
) -> AgentPromptSnapshot:
    prepared = await prepare_agent_prompt(
        conversation_id=conversation_id,
        question=question,
        skills=skills,
        custom_instructions=custom_instructions,
        include_draft_question=True,
    )
    return prepared.snapshot


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
    custom_instructions: str | None = None,
) -> dict:
    prepared = await prepare_agent_prompt(
        conversation_id=conversation_id,
        question=question,
        skills=skills,
        custom_instructions=custom_instructions,
    )
    messages = prepared.messages
    runtime_metrics = prepared.metrics

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
    custom_instructions: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    run_id = f"run_{uuid4().hex}"
    event_sequence = 0

    def sequenced(event: dict[str, Any]) -> dict[str, Any]:
        nonlocal event_sequence
        event_sequence += 1
        return {**event, "event_sequence": event_sequence, "run_id": run_id}

    prepared = await prepare_agent_prompt(
        conversation_id=conversation_id,
        question=question,
        skills=skills,
        custom_instructions=custom_instructions,
    )
    messages = prepared.messages
    yield sequenced(
        {
            "type": "run_started",
            "conversation_id": conversation_id,
        }
    )
    yield sequenced({"type": "context_metrics", **prepared.metrics})

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    streamed_any_token = False

    with bind_run_event_sink(
        queue,
        loop,
        run_id=run_id,
        conversation_id=conversation_id,
    ):
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
                yield sequenced(event)

            result = await run_task
        except Exception as exc:
            yield sequenced(
                {
                    "type": "run_error",
                    "error": str(exc),
                }
            )
            raise

    latency_ms = int((perf_counter() - start) * 1000)
    answer = _TRACE_EXTRACTOR.extract_answer(result)
    run_map = _TRACE_EXTRACTOR.build_run_map(result=result, total_latency_ms=latency_ms)

    print("FINAL ANSWER RUN MAP:", run_map)

    if not streamed_any_token:
        for token in _tokenize(answer):
            yield sequenced({"type": "token", "token": token})

    for event in _TRACE_EXTRACTOR.build_run_events(answer=answer, run_map=run_map):
        yield sequenced(event)

    yield sequenced(
        {
            "type": "run_finished",
            "duration_ms": latency_ms,
        }
    )

    # Persistence metadata consumed by API endpoint; not forwarded to client.
    yield {
        "type": "run_map",
        "run_id": run_id,
        "run_map": run_map,
        "answer": answer,
    }
