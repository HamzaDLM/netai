import asyncio
import json
from time import perf_counter
from typing import Any, AsyncIterator

from app.agents.orchestrator_agent import orchestrator_agent
from app.workflows.context_manager import build_conversation_context


def _extract_text(reply: Any) -> str:
    if reply is None:
        return ""
    text = getattr(reply, "text", None)
    if isinstance(text, str) and text:
        return text
    content = getattr(reply, "content", None)
    if isinstance(content, str) and content:
        return content
    if isinstance(reply, dict):
        content = reply.get("content") or reply.get("text")
        if isinstance(content, str):
            return content
    return str(reply)


def _extract_answer(result: Any) -> str:
    if isinstance(result, dict):
        replies = result.get("replies") or result.get("reply")
        if replies:
            if isinstance(replies, list):
                return _extract_text(replies[0])
            return _extract_text(replies)
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            return _extract_text(messages[-1])
        if "answer" in result:
            return _extract_text(result["answer"])
    return _extract_text(result)


def _extract_tool_calls(result: Any) -> list[dict]:
    def _to_json_object(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value}
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        return parsed
                    if isinstance(parsed, list):
                        return {"items": parsed}
                except Exception:
                    pass
            return {"value": value}
        if isinstance(value, (int, float, bool)):
            return {"value": value}
        return {"value": str(value)}

    def _extract_from_messages(messages: list[Any]) -> list[dict]:
        calls: list[dict] = []
        calls_by_id: dict[str, dict] = {}

        for message in messages:
            tool_calls = getattr(message, "tool_calls", None) or []
            for tool_call in tool_calls:
                call = {
                    "name": getattr(tool_call, "tool_name", "unknown_tool"),
                    "arguments": getattr(tool_call, "arguments", None),
                    "result": None,
                    "latency_ms": None,
                    "evidence": [],
                }
                calls.append(call)
                tool_call_id = getattr(tool_call, "id", None)
                if isinstance(tool_call_id, str) and tool_call_id:
                    calls_by_id[tool_call_id] = call

            tool_call_results = getattr(message, "tool_call_results", None) or []
            for tool_result in tool_call_results:
                origin = getattr(tool_result, "origin", None)
                origin_id = getattr(origin, "id", None) if origin is not None else None
                origin_name = (
                    getattr(origin, "tool_name", "unknown_tool")
                    if origin is not None
                    else "unknown_tool"
                )
                origin_arguments = (
                    getattr(origin, "arguments", None) if origin is not None else None
                )
                result_payload = _to_json_object(getattr(tool_result, "result", None))
                if result_payload is None:
                    result_payload = {}
                if getattr(tool_result, "error", False):
                    result_payload = {"error": True, "result": result_payload}

                target_call = None
                if isinstance(origin_id, str) and origin_id:
                    target_call = calls_by_id.get(origin_id)
                if target_call is None:
                    for existing in reversed(calls):
                        if (
                            existing.get("name") == origin_name
                            and existing.get("result") is None
                        ):
                            target_call = existing
                            break

                if target_call is None:
                    target_call = {
                        "name": origin_name,
                        "arguments": origin_arguments,
                        "result": None,
                        "latency_ms": None,
                        "evidence": [],
                    }
                    calls.append(target_call)
                    if isinstance(origin_id, str) and origin_id:
                        calls_by_id[origin_id] = target_call

                target_call["result"] = result_payload

        return calls

    raw: Any = None
    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            extracted = _extract_from_messages(messages)
            if extracted:
                return extracted
        raw = result.get("tool_calls") or result.get("tools")
    if raw is None:
        result_messages = getattr(result, "messages", None)
        if isinstance(result_messages, list) and result_messages:
            extracted = _extract_from_messages(result_messages)
            if extracted:
                return extracted
        raw = getattr(result, "tool_calls", None)
    if raw is None:
        return []

    calls: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            name = (
                item.get("name")
                or item.get("tool_name")
                or item.get("tool")
                or "unknown_tool"
            )
            calls.append(
                {
                    "name": name,
                    "arguments": item.get("arguments") or item.get("args"),
                    "result": _to_json_object(item.get("result")),
                    "latency_ms": item.get("latency_ms"),
                    "evidence": item.get("evidence") or [],
                }
            )
        else:
            calls.append(
                {
                    "name": getattr(item, "name", "unknown_tool"),
                    "arguments": getattr(item, "arguments", None),
                    "result": _to_json_object(getattr(item, "result", None)),
                    "latency_ms": getattr(item, "latency_ms", None),
                    "evidence": getattr(item, "evidence", []),
                }
            )
    return calls


def _extract_specialist_name(tool_name: str | None) -> str:
    if not tool_name:
        return "unknown"
    name = tool_name.strip().lower()
    if name.endswith("_specialist"):
        return name.removesuffix("_specialist")
    return name


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
        # Single source of truth for routing/delegation: orchestrator agent.
        kwargs: dict[str, Any] = {"messages": messages}
        if streaming_callback is not None:
            kwargs["streaming_callback"] = streaming_callback

        if run_in_thread:
            return await asyncio.to_thread(orchestrator_agent.run, **kwargs)
        return await _maybe_await(orchestrator_agent.run(**kwargs))
    except TypeError:
        raise Exception("problem with agent message type")


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


async def run_agent(*, conversation_id: int, question: str) -> dict:
    context = await build_conversation_context(conversation_id=conversation_id)
    messages = context.messages

    start = perf_counter()
    result = await _run_agent(messages)
    latency_ms = int((perf_counter() - start) * 1000)

    answer = _extract_answer(result)
    tools = _extract_tool_calls(result)
    for tool in tools:
        if tool.get("latency_ms") is None:
            tool["latency_ms"] = latency_ms

    return {"answer": answer, "tools": tools, "context_metrics": context.metrics()}


async def run_agent_stream(
    *, conversation_id: int, question: str
) -> AsyncIterator[dict]:
    context = await build_conversation_context(conversation_id=conversation_id)
    messages = context.messages
    yield {"type": "context_metrics", **context.metrics()}
    yield {
        "type": "thinking",
        "agent": "orchestrator",
        "status": "received",
        "message": "Orchestrator received the message and started planning.",
    }

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    streamed_any_token = False
    emitted_running_heartbeat = False

    def _streaming_callback(chunk: Any) -> None:
        # Called from the worker thread. We forward token content into an asyncio Queue
        # using call_soon_threadsafe so the async loop can safely consume it.
        content = getattr(chunk, "content", None)
        if isinstance(content, str) and content:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "token", "token": content},
            )

    # Execute the agent in background; callback pushes chunks while this task runs.
    run_task = asyncio.create_task(
        _run_agent(
            messages,
            streaming_callback=_streaming_callback,
            run_in_thread=True,
        )
    )
    yield {
        "type": "thinking",
        "agent": "orchestrator",
        "status": "running",
        "message": "Orchestrator is delegating work to specialists.",
    }

    while True:
        # Stop only when generation finished and there are no pending streamed events.
        if run_task.done() and queue.empty():
            break
        try:
            # Poll queue with a timeout so we can periodically re-check task completion.
            event = await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            if not emitted_running_heartbeat:
                emitted_running_heartbeat = True
                yield {
                    "type": "thinking",
                    "agent": "orchestrator",
                    "status": "running",
                    "message": "Still processing specialist responses...",
                }
            continue
        if event.get("type") == "token":
            streamed_any_token = True
        yield event

    # Final result still matters: we extract answer and tool calls for DB persistence + tool SSE.
    result = await run_task
    answer = _extract_answer(result)
    tools = _extract_tool_calls(result)

    # Fallback mode: some providers/models may not emit chunk callbacks even if a callback is set.
    # In that case we preserve previous behavior by tokenizing the final answer.
    if not streamed_any_token:
        for token in _tokenize(answer):
            yield {"type": "token", "token": token}

    specialist_calls = [
        tool
        for tool in tools
        if str(tool.get("name", "")).strip().lower().endswith("_specialist")
    ]
    if specialist_calls:
        yield {
            "type": "orchestrator_plan",
            "plan": "Delegate to specialist agents based on intent, then synthesize final answer.",
            "specialists": [
                _extract_specialist_name(str(tool.get("name")))
                for tool in specialist_calls
            ],
        }

    for tool in specialist_calls:
        specialist = _extract_specialist_name(str(tool.get("name")))
        prompt_payload = tool.get("arguments")
        result_payload = tool.get("result")
        yield {
            "type": "thinking",
            "agent": specialist,
            "status": "running",
            "message": f"{specialist} specialist is processing delegated task.",
        }

        yield {
            "type": "specialist_prompt",
            "specialist": specialist,
            "prompt": prompt_payload,
        }
        yield {
            "type": "specialist_thought",
            "specialist": specialist,
            "thought": result_payload,
        }
        yield {
            "type": "specialist_tool_call",
            "specialist": specialist,
            "tool_name": str(tool.get("name") or "unknown_tool"),
            "arguments": prompt_payload,
            "evidence": tool.get("evidence") or [],
        }
        if result_payload is not None:
            yield {
                "type": "specialist_tool_result",
                "specialist": specialist,
                "tool_name": str(tool.get("name") or "unknown_tool"),
                "result": result_payload,
            }
        yield {
            "type": "thinking",
            "agent": specialist,
            "status": "done",
            "message": f"{specialist} specialist finished.",
        }

    yield {
        "type": "thinking",
        "agent": "orchestrator",
        "status": "done",
        "message": "Orchestrator finished synthesis.",
    }
    yield {
        "type": "leader_conclusion",
        "answer": answer,
    }
