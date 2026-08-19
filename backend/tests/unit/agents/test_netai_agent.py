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

    async def close(self) -> None:
        return None


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
