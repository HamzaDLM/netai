import asyncio
from contextvars import ContextVar
from time import perf_counter
from typing import Any, AsyncIterator

from haystack.dataclasses import ChatMessage

from app.agents.orchestrator_agent import SPECIALIST_DESCRIPTIONS, orchestrator_agent
from app.prompts import FORMATTING_PROMPT
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
    _ = question
    context = await build_conversation_context(conversation_id=conversation_id)
    messages = _with_runtime_formatting_prompt(
        _with_runtime_skill_prompts(context.messages, skills)
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
        "context_metrics": context.metrics(),
    }


async def run_agent_stream(
    *,
    conversation_id: str,
    question: str,
    skills: list[SkillInstruction] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    _ = question
    context = await build_conversation_context(conversation_id=conversation_id)
    messages = _with_runtime_formatting_prompt(
        _with_runtime_skill_prompts(context.messages, skills)
    )
    yield {"type": "context_metrics", **context.metrics()}

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
