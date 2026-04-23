import ast
import dataclasses
import json
from typing import Any


class AgentTraceExtractor:
    def __init__(self, *, specialist_descriptions: dict[str, str] | None = None):
        self.specialist_descriptions = specialist_descriptions or {}

    def extract_answer(self, result: Any) -> str:
        if isinstance(result, dict):
            replies = result.get("replies") or result.get("reply")
            if replies:
                if isinstance(replies, list):
                    return self._extract_text(replies[0])
                return self._extract_text(replies)
            messages = result.get("messages")
            if isinstance(messages, list) and messages:
                return self._extract_text(messages[-1])
            if "answer" in result:
                return self._extract_text(result["answer"])
        return self._extract_text(result)

    def extract_tool_calls(self, result: Any) -> list[dict[str, Any]]:
        embedded_payload = self._extract_embedded_payload(result)
        if embedded_payload is not None:
            extracted = self.extract_tool_calls(embedded_payload)
            if extracted:
                return extracted

        if isinstance(result, dict):
            extracted_from_runs = self._extract_tool_calls_from_agent_runs(
                result.get("agent_runs")
            )
            if extracted_from_runs:
                return extracted_from_runs

        def _extract_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
            def _get(obj: Any, key: str, default: Any = None) -> Any:
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            calls: list[dict[str, Any]] = []
            calls_by_id: dict[str, dict[str, Any]] = {}

            for message in messages:
                tool_calls = _get(message, "tool_calls", None) or []
                tool_call_results = _get(message, "tool_call_results", None) or []

                # Support dict-style messages where tool calls are embedded in content parts
                # (e.g. persisted payloads serialized from ChatMessage objects).
                if isinstance(message, dict):
                    content_parts = message.get("content")
                    if isinstance(content_parts, list):
                        for part in content_parts:
                            if not isinstance(part, dict):
                                continue
                            embedded_tool_call = part.get("tool_call")
                            if isinstance(embedded_tool_call, dict):
                                tool_calls.append(embedded_tool_call)
                            embedded_tool_result = part.get("tool_call_result")
                            if isinstance(embedded_tool_result, dict):
                                tool_call_results.append(embedded_tool_result)

                for tool_call in tool_calls:
                    tool_call_evidence = self._extract_evidence_payload(
                        self._to_json_object(_get(tool_call, "result", None))
                    )
                    call: dict[str, Any] = {
                        "name": _get(tool_call, "tool_name", "unknown_tool"),
                        "arguments": _get(tool_call, "arguments", None),
                        "result": None,
                        "latency_ms": None,
                        "evidence": tool_call_evidence,
                    }
                    calls.append(call)
                    tool_call_id = _get(tool_call, "id", None)
                    if isinstance(tool_call_id, str) and tool_call_id:
                        calls_by_id[tool_call_id] = call

                for tool_result in tool_call_results:
                    origin = _get(tool_result, "origin", None)
                    origin_id = _get(origin, "id", None) if origin is not None else None
                    origin_name = (
                        _get(origin, "tool_name", "unknown_tool")
                        if origin is not None
                        else "unknown_tool"
                    )
                    origin_arguments = (
                        _get(origin, "arguments", None) if origin is not None else None
                    )
                    result_payload = self._to_json_object(
                        _get(tool_result, "result", None)
                    )
                    if result_payload is None:
                        result_payload = {}
                    if bool(_get(tool_result, "error", False)):
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
                    if not target_call.get("evidence"):
                        target_call["evidence"] = self._extract_evidence_payload(
                            result_payload
                        )

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

        calls: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("tool_name")
                    or item.get("tool")
                    or "unknown_tool"
                )
                result_payload = self._to_json_object(item.get("result"))
                calls.append(
                    {
                        "name": name,
                        "arguments": item.get("arguments") or item.get("args"),
                        "result": result_payload,
                        "latency_ms": item.get("latency_ms"),
                        "evidence": item.get("evidence")
                        or self._extract_evidence_payload(result_payload)
                        or [],
                    }
                )
                continue

            result_payload = self._to_json_object(getattr(item, "result", None))
            calls.append(
                {
                    "name": getattr(item, "name", "unknown_tool"),
                    "arguments": getattr(item, "arguments", None),
                    "result": result_payload,
                    "latency_ms": getattr(item, "latency_ms", None),
                    "evidence": getattr(item, "evidence", None)
                    or self._extract_evidence_payload(result_payload)
                    or [],
                }
            )
        return calls

    def _extract_tool_calls_from_agent_runs(
        self, agent_runs: Any
    ) -> list[dict[str, Any]]:
        if not isinstance(agent_runs, list):
            return []

        calls: list[dict[str, Any]] = []
        pending_by_specialist: dict[str, list[dict[str, Any]]] = {}

        for run in agent_runs:
            if not isinstance(run, dict):
                continue
            events = run.get("events")
            if not isinstance(events, list):
                continue

            for event in events:
                if not isinstance(event, dict):
                    continue
                event_type = str(event.get("event_type") or "").strip().lower()
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue

                specialist_name = str(payload.get("specialist") or "").strip().lower()
                if event_type == "specialist_tool_call":
                    name = str(payload.get("tool_name") or "").strip() or "unknown_tool"
                    call: dict[str, Any] = {
                        "name": name,
                        "arguments": payload.get("arguments") or {},
                        "result": None,
                        "latency_ms": None,
                        "evidence": [],
                    }
                    calls.append(call)
                    if specialist_name:
                        pending_by_specialist.setdefault(specialist_name, []).append(
                            call
                        )
                    continue

                if event_type != "specialist_evidence":
                    continue

                target_call: dict[str, Any] | None = None
                if specialist_name:
                    queue = pending_by_specialist.get(specialist_name) or []
                    for pending in queue:
                        if pending.get("result") is None:
                            target_call = pending
                            break

                if target_call is None:
                    # Fallback for partial payloads where tool_call event is missing.
                    name = str(payload.get("tool_name") or "").strip() or "unknown_tool"
                    target_call = {
                        "name": name,
                        "arguments": payload.get("arguments") or {},
                        "result": None,
                        "latency_ms": None,
                        "evidence": [],
                    }
                    calls.append(target_call)

                target_call["result"] = (
                    self._to_json_object(payload.get("result")) or {}
                )
                evidence = payload.get("evidence")
                target_call["evidence"] = (
                    evidence
                    if isinstance(evidence, list)
                    else self._extract_evidence_payload(target_call["result"])
                )

        return calls

    def _extract_embedded_payload(self, payload: Any) -> Any | None:
        if payload is None:
            return None

        parsed_from_string = (
            self._parse_jsonish(payload) if isinstance(payload, str) else None
        )
        if isinstance(parsed_from_string, (dict, list)):
            return parsed_from_string

        if isinstance(payload, list):
            return {"messages": payload} if payload else None

        if not isinstance(payload, dict):
            return None

        if any(key in payload for key in ("messages", "tool_calls", "tools")):
            return None

        for key in ("result", "output", "value", "text", "content"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                return {"messages": value} if value else None
            if isinstance(value, str):
                parsed = self._parse_jsonish(value)
                if isinstance(parsed, (dict, list)):
                    return parsed

        return None

    def build_run_map(self, *, result: Any, total_latency_ms: int) -> dict[str, Any]:
        tools = self.extract_tool_calls(result)
        specialist_calls = [
            tool
            for tool in tools
            if self._is_specialist_dispatch_tool(str(tool.get("name", "")))
        ]
        specialists = [
            self._extract_specialist_name(str(tool.get("name")))
            for tool in specialist_calls
        ]
        sub_agent_calls: list[dict[str, Any]] = []
        for call_sequence, tool in enumerate(specialist_calls, start=1):
            specialist = self._extract_specialist_name(str(tool.get("name")))
            prompt_payload = self.normalize_tool_arguments(tool.get("arguments"))
            task_prompt = self._extract_delegated_prompt_text(
                original_arguments=tool.get("arguments"),
                normalized_arguments=prompt_payload,
            )
            result_payload = tool.get("result")
            nested_calls = [
                nested
                for nested in self.extract_tool_calls(result_payload)
                if not self._is_specialist_dispatch_tool(str(nested.get("name", "")))
            ]
            normalized_result = self.normalize_result_payload(result_payload)
            tool_calls: list[dict[str, Any]] = []
            if nested_calls:
                for nested in nested_calls:
                    tool_calls.append(self._build_tool_call_row(nested))
            else:
                fallback = {
                    "name": str(tool.get("name") or "unknown_tool"),
                    "arguments": prompt_payload,
                    "result": result_payload,
                    "latency_ms": tool.get("latency_ms"),
                    "evidence": tool.get("evidence")
                    or self._extract_evidence_payload(result_payload)
                    or [],
                }
                fallback_row = self._build_tool_call_row(fallback)
                if not fallback_row.get("output"):
                    fallback_row["output"] = normalized_result
                tool_calls.append(fallback_row)

            failed = any(
                str(entry.get("status", "success")) in {"error", "timeout", "blocked"}
                for entry in tool_calls
            )
            sub_agent_calls.append(
                {
                    "specialist_name": specialist,
                    "call_sequence": call_sequence,
                    "task_prompt": task_prompt,
                    "plan": self._build_specialist_plan_text(
                        specialist=specialist,
                        task_prompt=task_prompt,
                    ),
                    "result_summary": self._summarize_specialist_result(
                        normalized_result=normalized_result,
                        tool_calls=tool_calls,
                    ),
                    "status": "error" if failed else "success",
                    "duration_ms": tool.get("latency_ms"),
                    "error_message": self._first_error_message(tool_calls),
                    "tool_calls": tool_calls,
                }
            )

        return {
            "orchestrator": {
                "agent_name": "orchestrator",
                "status": "completed",
                "duration_ms": total_latency_ms,
                "specialists": specialists,
                "reasoning": self._build_orchestrator_reasoning(specialists),
            },
            "sub_agent_calls": sub_agent_calls,
        }

    def build_run_events(
        self, *, answer: str, run_map: dict[str, Any]
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        orchestrator = run_map.get("orchestrator") or {}
        specialists = orchestrator.get("specialists") or []
        reasoning = orchestrator.get("reasoning")
        if specialists:
            events.append(
                {
                    "type": "orchestrator_decision",
                    "specialists": specialists,
                    "reasoning": reasoning,
                }
            )

        for sub_call in run_map.get("sub_agent_calls") or []:
            specialist = str(sub_call.get("specialist_name") or "unknown")
            events.append(
                {
                    "type": "specialist_plan",
                    "specialist": specialist,
                    "plan": sub_call.get("plan")
                    or self._build_specialist_plan_text(
                        specialist=specialist,
                        task_prompt=str(sub_call.get("task_prompt") or ""),
                    ),
                }
            )
            for tool_call in sub_call.get("tool_calls") or []:
                events.append(
                    {
                        "type": "specialist_tool_call",
                        "specialist": specialist,
                        "tool_name": str(tool_call.get("tool_name") or "unknown_tool"),
                        "arguments": tool_call.get("input_params") or {},
                    }
                )
                events.append(
                    {
                        "type": "specialist_evidence",
                        "specialist": specialist,
                        "tool_name": str(tool_call.get("tool_name") or "unknown_tool"),
                        "result": tool_call.get("output") or {},
                        "evidence": tool_call.get("evidence") or [],
                    }
                )

        events.append({"type": "leader_conclusion", "answer": answer})
        return events

    def _build_tool_call_row(self, call: dict[str, Any]) -> dict[str, Any]:
        result_payload = call.get("result")
        output = self.normalize_result_payload(result_payload)
        evidence = (
            call.get("evidence") or self._extract_evidence_payload(result_payload) or []
        )
        status = self._resolve_tool_status(result_payload)
        error_type, error_message = self._extract_error_fields(result_payload)
        return {
            "tool_name": str(call.get("name") or "unknown_tool"),
            "input_params": self.normalize_tool_arguments(call.get("arguments")),
            "output": output,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "latency_ms": call.get("latency_ms"),
            "evidence": evidence,
        }

    def _extract_text(self, reply: Any) -> str:
        if reply is None:
            return ""
        text = getattr(reply, "text", None)
        if isinstance(text, str) and text:
            return text
        content = getattr(reply, "content", None)
        if isinstance(content, str) and content:
            return content
        if isinstance(reply, dict):
            dict_content = reply.get("content") or reply.get("text")
            if isinstance(dict_content, str):
                return dict_content
        return str(reply)

    def _extract_evidence_payload(self, payload: Any) -> list[Any]:
        queue: list[Any] = [payload]
        visited_ids: set[int] = set()
        while queue:
            current = queue.pop(0)
            current_id = id(current)
            if current_id in visited_ids:
                continue
            visited_ids.add(current_id)
            if isinstance(current, list):
                if current and all(
                    isinstance(item, (dict, str, int, float, bool)) for item in current
                ):
                    return current
                queue.extend(current)
                continue
            if not isinstance(current, dict):
                continue

            for key in ("evidence", "evidence_items"):
                value = current.get(key)
                if isinstance(value, list):
                    return value
                if isinstance(value, dict):
                    queue.append(value)
                elif isinstance(value, str):
                    parsed = self._parse_jsonish(value)
                    if parsed is not None:
                        queue.append(parsed)

            for nested in current.values():
                if isinstance(nested, (dict, list)):
                    queue.append(nested)
                    continue
                if isinstance(nested, str):
                    parsed = self._parse_jsonish(nested)
                    if parsed is not None:
                        queue.append(parsed)
        return []

    def _to_json_object(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return self._to_json_object(dataclasses.asdict(value))
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            try:
                return self._to_json_object(model_dump())
            except Exception:
                pass
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                return self._to_json_object(to_dict())
            except Exception:
                pass
        as_dict = getattr(value, "__dict__", None)
        if isinstance(as_dict, dict) and as_dict:
            return self._to_json_object(as_dict)
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value}
        if isinstance(value, str):
            parsed = self._parse_jsonish(value)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
            return {"value": value}
        if isinstance(value, (int, float, bool)):
            return {"value": value}
        return {"value": str(value)}

    def _parse_jsonish(self, value: str) -> Any:
        stripped = value.strip()
        if not stripped:
            return None
        if not (stripped.startswith("{") or stripped.startswith("[")):
            return None
        try:
            return json.loads(stripped)
        except Exception:
            try:
                return ast.literal_eval(stripped)
            except Exception:
                pass
            normalized = (
                stripped.replace("'", '"')
                .replace("\\'", "'")
                .replace("None", "null")
                .replace("True", "true")
                .replace("False", "false")
            )
            try:
                return json.loads(normalized)
            except Exception:
                return None

    def _extract_specialist_name(self, tool_name: str | None) -> str:
        if not tool_name:
            return "unknown"
        name = tool_name.strip().lower()
        if name.endswith("_specialist"):
            return name.removesuffix("_specialist")
        if name.endswith("_agent"):
            return name.removesuffix("_agent")
        return name

    def _is_specialist_dispatch_tool(self, tool_name: str | None) -> bool:
        if not tool_name:
            return False
        name = tool_name.strip().lower()
        if name.endswith("_specialist"):
            return True
        # Compatibility path: older traces may use "<specialist>_agent".
        if (
            name.endswith("_agent")
            and name.removesuffix("_agent") in self.specialist_descriptions
        ):
            return True
        return False

    def normalize_tool_arguments(self, arguments: Any) -> dict[str, Any]:
        if not isinstance(arguments, dict):
            return {}
        messages = arguments.get("messages")
        if isinstance(messages, list) and messages:
            first = messages[0]
            if isinstance(first, dict):
                content = first.get("content")
                if isinstance(content, str) and content.strip():
                    return {"question": content.strip()}
                if isinstance(content, dict):
                    text = content.get("text")
                    if isinstance(text, str) and text.strip():
                        return {"question": text.strip()}
                if isinstance(content, list) and content:
                    first_part = content[0]
                    if isinstance(first_part, dict):
                        text = first_part.get("text")
                        if isinstance(text, str) and text.strip():
                            return {"question": text.strip()}
        return arguments

    def normalize_result_payload(self, result_payload: Any) -> dict[str, Any]:
        payload = result_payload
        if isinstance(payload, dict) and "value" in payload:
            payload = payload.get("value")
        if isinstance(payload, str):
            parsed = self._parse_jsonish(payload)
            if parsed is not None:
                payload = parsed
            else:
                text_value = payload.strip()
                return {"text": text_value} if text_value else {}
        if isinstance(payload, dict):
            payload_text = self._extract_text_from_payload(payload)
            if payload_text:
                return {"text": payload_text}
            return payload
        if isinstance(payload, list):
            return {"items": payload}
        if payload is None:
            return {}
        return {"value": payload}

    def _extract_error_fields(
        self, result_payload: Any
    ) -> tuple[str | None, str | None]:
        payload = self.normalize_result_payload(result_payload)
        if payload.get("error") is True:
            nested = payload.get("result")
            if isinstance(nested, dict):
                code = nested.get("error_type") or nested.get("code")
                msg = nested.get("error_message") or nested.get("message")
                return (
                    str(code) if code is not None else "tool_error",
                    str(msg) if msg is not None else "tool execution failed",
                )
            return "tool_error", "tool execution failed"
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return "tool_error", error.strip()
        error_message = payload.get("error_message")
        if isinstance(error_message, str) and error_message.strip():
            code = payload.get("error_type") or payload.get("code") or "tool_error"
            return str(code), error_message.strip()
        return None, None

    def _resolve_tool_status(self, result_payload: Any) -> str:
        error_type, error_message = self._extract_error_fields(result_payload)
        if error_type or error_message:
            return "error"
        payload = self.normalize_result_payload(result_payload)
        value = payload.get("status")
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"error", "failed", "failure"}:
                return "error"
            if lowered in {"timeout", "timed_out"}:
                return "timeout"
            if lowered in {"blocked", "requires_approval"}:
                return "blocked"
        return "success"

    def _build_orchestrator_reasoning(self, specialists: list[str]) -> str:
        if not specialists:
            return "No specialist delegation was required."
        reasons: list[str] = []
        for specialist in specialists:
            description = self.specialist_descriptions.get(specialist)
            if description:
                reasons.append(f"{specialist}: {description}")
            else:
                reasons.append(f"{specialist}: selected for domain-specific analysis.")
        return "Delegation rationale: " + " ".join(reasons)

    def _extract_delegated_prompt_text(
        self, *, original_arguments: Any, normalized_arguments: dict[str, Any]
    ) -> str:
        question = normalized_arguments.get("question")
        if isinstance(question, str) and question.strip():
            return question.strip()
        if isinstance(original_arguments, dict):
            messages = original_arguments.get("messages")
            if isinstance(messages, list) and messages:
                first = messages[0]
                if isinstance(first, dict):
                    content = first.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()
        if normalized_arguments:
            try:
                return json.dumps(normalized_arguments, ensure_ascii=True)
            except Exception:
                return str(normalized_arguments)
        return "Delegated specialist task"

    def _build_specialist_plan_text(self, *, specialist: str, task_prompt: str) -> str:
        if task_prompt.strip():
            return (
                f"Plan: analyze '{task_prompt.strip()}' using {specialist} domain tools "
                "and return evidence-backed findings."
            )
        return (
            f"Plan: run the minimum {specialist} tool calls needed to answer and "
            "return evidence-backed findings."
        )

    def _extract_text_from_payload(self, payload: dict[str, Any]) -> str | None:
        text = payload.get("text") or payload.get("content")
        if isinstance(text, str) and text.strip():
            return text.strip()
        content = payload.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_text = item.get("text") or item.get("content")
                if isinstance(item_text, str) and item_text.strip():
                    parts.append(item_text.strip())
            if parts:
                return "\n".join(parts)
        return None

    def _summarize_specialist_result(
        self, *, normalized_result: dict[str, Any], tool_calls: list[dict[str, Any]]
    ) -> str | None:
        text = normalized_result.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        for call in reversed(tool_calls):
            output = call.get("output")
            if isinstance(output, dict):
                output_text = output.get("text")
                if isinstance(output_text, str) and output_text.strip():
                    return output_text.strip()
            error_message = call.get("error_message")
            if isinstance(error_message, str) and error_message.strip():
                return error_message.strip()
        return None

    def _first_error_message(self, tool_calls: list[dict[str, Any]]) -> str | None:
        for call in tool_calls:
            message = call.get("error_message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return None
