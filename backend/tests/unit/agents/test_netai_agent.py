from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest
from haystack import component
from haystack.components.agents import State
from haystack.dataclasses import ChatMessage, ToolCall
from haystack.tools import Tool, Toolset

from app.agents.netai import ToolAuthorizationError, authorize_and_observe_tools
from app.core.config import project_settings
from app.mcp.mcp_client import (
    MCPPromptContext,
    MCPRequestContext,
    MCPResourceContext,
)
from app.services.chat_agent import build_runtime_prompt_snapshot
from app.services.netai import NetAIService
from app.tools.registry import ToolRegistry


@component
class ScriptedGenerator:
    def __init__(self, replies: Sequence[ChatMessage]) -> None:
        self.replies = list(replies)
        self.calls = 0
        self.tools_seen: list[set[str]] = []
        self.messages_seen: list[list[ChatMessage]] = []
        self.closed = False

    def warm_up(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    @component.output_types(replies=list[ChatMessage])
    def run(
        self,
        messages: list[ChatMessage],
        tools: Toolset | list[Tool] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        raise AssertionError("The async Agent path must not call ChatGenerator.run()")

    @component.output_types(replies=list[ChatMessage])
    async def run_async(
        self,
        messages: list[ChatMessage],
        tools: Toolset | list[Tool] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        self.messages_seen.append(list(messages))
        visible = list(tools) if tools is not None else []
        self.tools_seen.append({registered_tool.name for registered_tool in visible})
        reply = self.replies[self.calls]
        self.calls += 1
        return {"replies": [reply]}


def _dynamic_tool_script() -> list[ChatMessage]:
    return [
        ChatMessage.from_assistant(
            tool_calls=[
                ToolCall(
                    tool_name="search_tools",
                    arguments={"tool_keywords": "topology devices"},
                    id="search-1",
                )
            ]
        ),
        ChatMessage.from_assistant(
            tool_calls=[
                ToolCall(
                    tool_name="datamodel_list_devices",
                    arguments={},
                    id="tool-1",
                )
            ]
        ),
        ChatMessage.from_assistant("Topology inventory retrieved."),
    ]


@pytest.mark.anyio
async def test_service_uses_native_agent_loop_and_dynamic_tool_discovery() -> None:
    generator = ScriptedGenerator(_dynamic_tool_script())
    service = NetAIService(settings=project_settings, chat_generator=generator)
    try:
        await service.warm_up()
        run = await service.run(
            messages=[ChatMessage.from_user("List topology devices")],
            conversation_id="conversation-test",
            user_id=7,
            request_id="request-test",
        )
    finally:
        await service.close()

    assert run.answer == "Topology inventory retrieved."
    assert run.result["step_count"] == 3
    assert run.result["tool_call_counts"] == {
        "search_tools": 1,
        "datamodel_list_devices": 1,
    }
    assert generator.tools_seen[0] == {"search_tools"}
    assert "datamodel_list_devices" in generator.tools_seen[1]
    first_prompt = "\n".join(
        message.text or "" for message in generator.messages_seen[0]
    )
    second_prompt = "\n".join(
        message.text or "" for message in generator.messages_seen[1]
    )
    final_prompt = "\n".join(
        message.text or "" for message in generator.messages_seen[2]
    )
    assert "Tool group guidance" not in first_prompt
    assert second_prompt.count("Tool group guidance [datamodel]") == 1
    assert "modeled or intended structure" in second_prompt
    assert final_prompt.count("Tool group guidance [datamodel]") == 1
    assert "Tool group guidance [zabbix]" not in second_prompt
    runtime_snapshot = build_runtime_prompt_snapshot(
        result=run.result,
        metrics={"used_tokens": 10},
    )
    assert "Tool group guidance [datamodel]" in runtime_snapshot.messages[0].text
    assert any(
        message.source == "assistant_tool_call"
        and "datamodel_list_devices" in message.text
        for message in runtime_snapshot.messages
    )
    assert runtime_snapshot.messages[-1].source == "assistant_response"
    assert runtime_snapshot.messages[-1].text == "Topology inventory retrieved."
    tool_calls = cast(list[dict[str, object]], run.run_map["tool_calls"])
    assert [call["tool_name"] for call in tool_calls] == ["datamodel_list_devices"]
    assert generator.closed is True
    assert service.clients.http.is_closed is True
    assert service.clients.insecure_http.is_closed is True


@pytest.mark.anyio
async def test_authorization_hook_rejects_tool_outside_request_catalog() -> None:
    registry = ToolRegistry(project_settings)
    state = State(
        schema={},
        data={
            "messages": [
                ChatMessage.from_assistant(
                    tool_calls=[ToolCall("unknown_write_tool", {}, "blocked-1")]
                )
            ],
            "hook_context": {
                "allowed_tool_names": registry.tool_names | {"search_tools"},
                "registry": registry,
            },
        },
    )

    with pytest.raises(ToolAuthorizationError, match="not authorized"):
        await authorize_and_observe_tools.run_async(state)


class UnavailableInfrahub:
    status_message = "Infrahub is currently unavailable."

    @staticmethod
    def is_relevant(_text: str) -> bool:
        return True

    async def get_toolset(self):
        return None

    async def request_context(self, _query: str) -> MCPRequestContext:
        return MCPRequestContext()

    async def close(self) -> None:
        return None


class UnavailableSuzieQ:
    status_message = "SuzieQ is currently unavailable."

    @staticmethod
    def is_relevant(_text: str) -> bool:
        return True

    async def get_toolset(self):
        return None

    async def request_context(self, _query: str) -> MCPRequestContext:
        return MCPRequestContext()

    async def close(self) -> None:
        return None


def test_selected_mcp_context_is_inserted_before_current_user_request() -> None:
    messages = [
        ChatMessage.from_system("Core policy"),
        ChatMessage.from_user("Diagnose edge-01 routing"),
    ]
    context = MCPRequestContext(
        prompts=(
            MCPPromptContext(
                server="Inventory",
                name="routing_diagnostic",
                text="Inspect intended routing first.",
            ),
        ),
        resources=(
            MCPResourceContext(
                server="Inventory",
                uri="schema://routing",
                name="routing_schema",
                text="device -> interface -> route",
            ),
        ),
    )

    enriched = NetAIService._with_mcp_context(messages, context)

    assert enriched[-1] is messages[-1]
    assert enriched[1].is_from("system")
    assert "Inspect intended routing first" in (enriched[1].text or "")
    assert enriched[2].is_from("user")
    assert "untrusted reference data" in (enriched[2].text or "")
    assert "device -> interface -> route" in (enriched[2].text or "")


@pytest.mark.anyio
async def test_optional_mcp_failure_does_not_block_agent() -> None:
    generator = ScriptedGenerator([ChatMessage.from_assistant("Used local data.")])
    service = NetAIService(
        settings=project_settings,
        chat_generator=generator,
        infrahub=UnavailableInfrahub(),  # type: ignore[arg-type]
    )
    try:
        run = await service.run(
            messages=[ChatMessage.from_user("Check Infrahub topology")],
            conversation_id="conversation-test",
            user_id=7,
        )
    finally:
        await service.close()

    assert run.answer == "Used local data."
    assert any(
        "Infrahub is currently unavailable" in (message.text or "")
        for message in generator.messages_seen[0]
    )


@pytest.mark.anyio
async def test_optional_suzieq_mcp_failure_falls_back_without_blocking() -> None:
    generator = ScriptedGenerator([ChatMessage.from_assistant("Used local data.")])
    service = NetAIService(
        settings=project_settings,
        chat_generator=generator,
        suzieq=UnavailableSuzieQ(),  # type: ignore[arg-type]
    )
    try:
        run = await service.run(
            messages=[ChatMessage.from_user("Check SuzieQ BGP sessions")],
            conversation_id="conversation-suzieq-fallback",
            user_id=7,
        )
    finally:
        await service.close()

    assert run.answer == "Used local data."
    assert any(
        "SuzieQ is currently unavailable" in (message.text or "")
        for message in generator.messages_seen[0]
    )


@component
class FailingGenerator:
    def warm_up(self) -> None:
        return None

    @component.output_types(replies=list[ChatMessage])
    def run(
        self,
        messages: list[ChatMessage],
        tools: Toolset | list[Tool] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        raise AssertionError("sync path invoked")

    @component.output_types(replies=list[ChatMessage])
    async def run_async(
        self,
        messages: list[ChatMessage],
        tools: Toolset | list[Tool] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        raise RuntimeError("provider unavailable")


@pytest.mark.anyio
async def test_agent_provider_error_propagates_to_application_boundary() -> None:
    service = NetAIService(settings=project_settings, chat_generator=FailingGenerator())
    try:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await service.run(
                messages=[ChatMessage.from_user("hello")],
                conversation_id="conversation-test",
                user_id=7,
            )
    finally:
        await service.close()


@pytest.mark.anyio
async def test_max_step_tool_run_gets_a_final_synthesis() -> None:
    tool_steps = [
        ChatMessage.from_assistant(
            tool_calls=[
                ToolCall(
                    tool_name="search_tools",
                    arguments={"tool_keywords": "topology devices"},
                    id="search-0",
                )
            ]
        ),
        *[
            ChatMessage.from_assistant(
                tool_calls=[
                    ToolCall(
                        tool_name="datamodel_list_devices",
                        arguments={},
                        id=f"devices-{index}",
                    )
                ]
            )
            for index in range(11)
        ],
    ]
    generator = ScriptedGenerator(
        [
            *tool_steps,
            ChatMessage.from_assistant(
                "The available topology evidence is incomplete, but the successful "
                "queries identified the relevant nodes."
            ),
        ]
    )
    service = NetAIService(settings=project_settings, chat_generator=generator)
    try:
        run = await service.run(
            messages=[
                ChatMessage.from_user("What is in the inventory?"),
                ChatMessage.from_assistant("A previous turn's answer."),
                ChatMessage.from_user("Inspect the topology inventory"),
            ],
            conversation_id="conversation-max-steps",
            user_id=7,
        )
    finally:
        await service.close()

    assert run.result["step_count"] == 12
    assert run.result["finalization_performed"] is True
    assert generator.calls == 13
    assert run.answer.startswith("The available topology evidence")
