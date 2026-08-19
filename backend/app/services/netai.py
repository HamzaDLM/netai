"""Application-owned runtime for the Haystack Agent and shared integrations."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from time import perf_counter
from typing import cast
from uuid import uuid4

from haystack.components.generators.chat.types import ChatGenerator
from haystack.dataclasses import ChatMessage, StreamingChunk
from haystack.tools import SearchableToolset
from haystack.utils import Secret
from haystack_integrations.components.generators.google_genai import (
    GoogleGenAIChatGenerator,
)

from app.agents.netai import create_netai_agent
from app.core.config import Settings
from app.infrastructure import InfrastructureClients
from app.mcp.infrahub import InfrahubToolProvider
from app.mcp.mcp_client import MCPClientConfig
from app.services.agent_events import RunObserver
from app.tools.registry import ToolRegistry


@dataclass(slots=True)
class NetAIRun:
    answer: str
    duration_ms: int
    result: dict[str, object]
    observer: RunObserver

    @property
    def run_map(self) -> dict[str, object]:
        public_tools = [
            execution.as_dict()
            for execution in self.observer.tool_executions
            if execution.connector != "internal"
        ]
        return {
            "agent": {
                "agent_name": "netai",
                "status": "completed",
                "duration_ms": self.duration_ms,
                "step_count": self.result.get("step_count", 0),
                "token_usage": self.result.get("token_usage", {}),
                "tool_call_counts": self.result.get("tool_call_counts", {}),
            },
            "tool_calls": public_tools,
        }


def create_chat_generator(settings: Settings) -> ChatGenerator:
    """Construct the configured native Haystack ChatGenerator."""

    api_key = (
        Secret.from_token(settings.GEMINI_API_KEY)
        if settings.GEMINI_API_KEY
        else Secret.from_env_var(["GOOGLE_API_KEY", "GEMINI_API_KEY"], strict=False)
    )
    return GoogleGenAIChatGenerator(
        api_key=api_key,
        model=settings.GEMINI_MODEL,
        generation_kwargs={"temperature": 0.1},
    )


class NetAIService:
    """Own the Agent, generator, tool registry, and connector lifecycle."""

    def __init__(
        self,
        *,
        settings: Settings,
        chat_generator: ChatGenerator | None = None,
        registry: ToolRegistry | None = None,
        infrahub: InfrahubToolProvider | None = None,
    ) -> None:
        self.settings = settings
        self.chat_generator = chat_generator or create_chat_generator(settings)
        self.registry = registry or ToolRegistry(settings)
        self.clients = InfrastructureClients()
        self.infrahub = infrahub or InfrahubToolProvider(
            MCPClientConfig(
                url=settings.INFRAHUB_MCP_URL,
                token=settings.INFRAHUB_MCP_TOKEN or None,
                timeout=settings.INFRAHUB_MCP_TIMEOUT_SECONDS,
            )
        )
        self.agent = create_netai_agent(
            chat_generator=self.chat_generator,
            registry=self.registry,
        )

    async def warm_up(self) -> None:
        """Warm local Agent resources without touching optional MCP connectors."""

        await self.agent.warm_up_async()

    async def close(self) -> None:
        try:
            await self.infrahub.close()
        finally:
            try:
                await self.clients.close()
            finally:
                close_async = getattr(self.chat_generator, "close_async", None)
                if callable(close_async):
                    await close_async()
                else:
                    close = getattr(self.chat_generator, "close", None)
                    if callable(close):
                        result = close()
                        if inspect.isawaitable(result):
                            await result

    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        generation_kwargs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Use the shared generator for title and context-summary requests."""

        run_async = getattr(self.chat_generator, "run_async", None)
        if not callable(run_async):
            raise TypeError("The configured ChatGenerator must support run_async()")
        result = await run_async(
            messages=messages,
            generation_kwargs=generation_kwargs,
        )
        return cast(dict[str, object], result)

    @staticmethod
    def _message_text(messages: list[ChatMessage]) -> str:
        return "\n".join(message.text or "" for message in messages)

    async def _tools_for_run(
        self,
        messages: list[ChatMessage],
        observer: RunObserver,
    ) -> tuple[SearchableToolset, str | None, set[str]]:
        allowed_names = self.registry.tool_names | {"search_tools"}
        if not self.infrahub.is_relevant(self._message_text(messages)):
            return self.registry.searchable_with(), None, allowed_names

        remote = await self.infrahub.get_toolset()
        if remote is None:
            return (
                self.registry.searchable_with(),
                self.infrahub.status_message,
                allowed_names,
            )

        remote_names = {remote_tool.name for remote_tool in remote.tools}
        observer.register_external_tools(remote_names, connector="infrahub")
        return (
            self.registry.searchable_with(remote),
            None,
            allowed_names | remote_names,
        )

    @staticmethod
    def _with_connector_notice(
        messages: list[ChatMessage], notice: str | None
    ) -> list[ChatMessage]:
        if not notice:
            return messages
        connector_message = ChatMessage.from_system(
            f"Optional connector status: {notice} Do not invent Infrahub evidence; "
            "continue with other available sources when useful."
        )
        if messages:
            return [*messages[:-1], connector_message, messages[-1]]
        return [connector_message]

    @staticmethod
    def _answer_from(result: dict[str, object]) -> str:
        last_message = result.get("last_message")
        if isinstance(last_message, ChatMessage):
            return (last_message.text or "").strip()
        messages = result.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, ChatMessage) and message.text:
                    return message.text.strip()
        return ""

    async def run(
        self,
        *,
        messages: list[ChatMessage],
        conversation_id: str,
        user_id: int,
        request_id: str | None = None,
        observer: RunObserver | None = None,
        stream: bool = False,
    ) -> NetAIRun:
        """Run the native async Agent with request-scoped tools, state, and hooks."""

        resolved_request_id = request_id or uuid4().hex
        run_observer = observer or RunObserver(
            run_id=f"run_{uuid4().hex}",
            conversation_id=conversation_id,
        )
        selected_tools, connector_notice, allowed_names = await self._tools_for_run(
            messages, run_observer
        )
        run_messages = self._with_connector_notice(messages, connector_notice)

        async def handle_chunk(chunk: StreamingChunk) -> None:
            custom_event = chunk.meta.get("netai_event")
            if isinstance(custom_event, dict):
                event_type = custom_event.get("type")
                if isinstance(event_type, str) and event_type:
                    await run_observer.emit(
                        event_type,
                        {
                            str(key): value
                            for key, value in custom_event.items()
                            if key != "type"
                        },
                    )
                return
            if chunk.content:
                await run_observer.emit("token", {"token": chunk.content})

        started_at = perf_counter()
        result = await self.agent.run_async(
            messages=run_messages,
            streaming_callback=handle_chunk if stream else None,
            tools=selected_tools,
            hook_context={
                "observer": run_observer,
                "registry": self.registry,
                "allowed_tool_names": allowed_names,
                "clients": self.clients,
            },
            request_id=resolved_request_id,
            user_id=user_id,
        )
        duration_ms = max(0, int(round((perf_counter() - started_at) * 1000)))
        return NetAIRun(
            answer=self._answer_from(result),
            duration_ms=duration_ms,
            result=result,
            observer=run_observer,
        )
