"""Capability-aware clients for MCP servers consumed by NetAI.

The provider owns one persistent MCP session. Startup discovers metadata only;
prompt and resource contents are retrieved selectively for relevant requests.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from time import monotonic
from typing import Any
from uuid import UUID

from fastmcp import Client as FastMCPClient
from fastmcp.client.transports import StreamableHttpTransport
from haystack.tools import Tool, Toolset
from mcp import types as mcp_types

logger = logging.getLogger(__name__)

_MUTATING_TOOL_WORDS = frozenset(
    {
        "add",
        "apply",
        "create",
        "delete",
        "disable",
        "enable",
        "execute",
        "install",
        "modify",
        "patch",
        "remove",
        "restart",
        "set",
        "start",
        "stop",
        "update",
        "write",
    }
)
_SEARCH_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "assistant",
        "current",
        "data",
        "for",
        "from",
        "get",
        "information",
        "list",
        "network",
        "of",
        "on",
        "please",
        "prompt",
        "read",
        "resource",
        "server",
        "show",
        "the",
        "to",
        "tool",
        "with",
    }
)
_WORD_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class MCPClientConfig:
    """Connection and content-cache settings for one consumed MCP server."""

    url: str
    token: str | None = None
    headers: dict[str, str] | None = None
    timeout: float = 30.0
    resource_cache_ttl_seconds: float = 60.0
    max_context_chars: int = 20_000


@dataclass(frozen=True, slots=True)
class MCPCapabilities:
    tools: bool = False
    prompts: bool = False
    resources: bool = False


@dataclass(frozen=True, slots=True)
class MCPPromptMetadata:
    name: str
    title: str | None
    description: str | None
    required_arguments: tuple[str, ...]

    @property
    def search_text(self) -> str:
        return " ".join(filter(None, (self.name, self.title, self.description)))


@dataclass(frozen=True, slots=True)
class MCPResourceMetadata:
    uri: str
    name: str
    title: str | None
    description: str | None
    mime_type: str | None

    @property
    def search_text(self) -> str:
        return " ".join(
            filter(None, (self.uri, self.name, self.title, self.description))
        )


@dataclass(frozen=True, slots=True)
class MCPPromptContext:
    server: str
    name: str
    text: str


@dataclass(frozen=True, slots=True)
class MCPResourceContext:
    server: str
    uri: str
    name: str
    text: str


@dataclass(frozen=True, slots=True)
class MCPRequestContext:
    prompts: tuple[MCPPromptContext, ...] = ()
    resources: tuple[MCPResourceContext, ...] = ()


@dataclass(frozen=True, slots=True)
class _ResourceCacheEntry:
    text: str
    expires_at: float


MCPClientFactory = Callable[[MCPClientConfig], FastMCPClient[Any]]


def create_mcp_client(config: MCPClientConfig) -> FastMCPClient[Any]:
    """Create a persistent FastMCP client without opening its session."""

    headers = dict(config.headers or {})
    transport = StreamableHttpTransport(
        config.url,
        headers=headers or None,
        auth=config.token,
    )
    return FastMCPClient(
        transport,
        timeout=config.timeout,
        init_timeout=config.timeout,
    )


def _tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in _WORD_PATTERN.findall(value.lower()):
        variants = {token}
        if len(token) > 3 and token.endswith("ies"):
            variants.add(f"{token[:-3]}y")
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            variants.add(token[:-1])
        tokens.update(
            variant for variant in variants if variant not in _SEARCH_STOP_WORDS
        )
    return tokens


def _relevance_score(query: str, candidate: str) -> int:
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0
    overlap = query_tokens & candidate_tokens
    score = len(overlap)
    candidate_lower = candidate.lower()
    for token in overlap:
        if token in candidate_lower:
            score += 1
    return score


def _is_read_only_tool(name: str) -> bool:
    return not (_tokens(name) & _MUTATING_TOOL_WORDS)


def _dump_content(content: object) -> str:
    model_dump = getattr(content, "model_dump", None)
    if callable(model_dump):
        return json.dumps(model_dump(mode="json"), default=str)
    return str(content)


def _json_compatible(value: object) -> object:
    """Preserve MCP result data while converting typed models to JSON values."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return _json_compatible(value.value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_compatible(dataclasses.asdict(value))

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_compatible(model_dump(mode="json"))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_compatible(to_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_compatible(item) for item in value]
    return str(value)


class OptionalMCPToolProvider:
    """Persistent, failure-isolated MCP client used by NetAI's agent runtime."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        connector: str,
        display_name: str,
        retry_after_seconds: float = 30.0,
        client_factory: MCPClientFactory = create_mcp_client,
    ) -> None:
        self.config = config
        self.connector = connector
        self.display_name = display_name
        self.retry_after_seconds = retry_after_seconds
        self._client_factory = client_factory
        self._client: FastMCPClient[Any] | None = None
        self._toolset: Toolset | None = None
        self._prompt_metadata: tuple[MCPPromptMetadata, ...] = ()
        self._resource_metadata: tuple[MCPResourceMetadata, ...] = ()
        self._capabilities = MCPCapabilities()
        self._prompt_cache: dict[str, str] = {}
        self._resource_cache: dict[str, _ResourceCacheEntry] = {}
        self._lock = asyncio.Lock()
        self._last_attempt_at = float("-inf")
        self._status = "not_checked"
        self.status_message = f"{display_name} MCP has not been checked."

    @property
    def capabilities(self) -> MCPCapabilities:
        return self._capabilities

    @property
    def status(self) -> str:
        return self._status

    @property
    def toolset(self) -> Toolset | None:
        return self._toolset

    @property
    def prompt_metadata(self) -> tuple[MCPPromptMetadata, ...]:
        return self._prompt_metadata

    @property
    def resource_metadata(self) -> tuple[MCPResourceMetadata, ...]:
        return self._resource_metadata

    async def warm_up(self, *, force: bool = False) -> bool:
        """Connect once and cache advertised capability metadata for this session."""

        if self._client is not None:
            return True
        now = monotonic()
        if not force and now - self._last_attempt_at < self.retry_after_seconds:
            return False

        async with self._lock:
            if self._client is not None:
                return True
            now = monotonic()
            if not force and now - self._last_attempt_at < self.retry_after_seconds:
                return False
            self._last_attempt_at = now
            client = self._client_factory(self.config)
            try:
                await client.__aenter__()
                initialize_result = client.initialize_result
                if initialize_result is None:
                    raise RuntimeError("MCP session did not return initialize metadata")
                advertised = initialize_result.capabilities
                supports_tools = advertised.tools is not None
                supports_prompts = advertised.prompts is not None
                supports_resources = advertised.resources is not None

                tools = await self._discover_tools(client) if supports_tools else []
                prompts = (
                    await self._discover_prompts(client) if supports_prompts else []
                )
                resources = (
                    await self._discover_resources(client) if supports_resources else []
                )

                self._client = client
                self._toolset = self._build_toolset(tools)
                self._prompt_metadata = tuple(prompts)
                self._resource_metadata = tuple(resources)
                self._capabilities = MCPCapabilities(
                    tools=supports_tools,
                    prompts=supports_prompts,
                    resources=supports_resources,
                )
                self.status_message = (
                    f"{self.display_name} MCP is available "
                    f"({len(self._toolset.tools)} tools, {len(prompts)} prompts, "
                    f"{len(resources)} resources)."
                )
                self._status = "available"
                logger.info(
                    "%s MCP metadata discovered: %d tools, %d prompts, %d resources",
                    self.display_name,
                    len(self._toolset.tools),
                    len(prompts),
                    len(resources),
                )
                return True
            except Exception as exc:
                try:
                    await client.__aexit__(type(exc), exc, exc.__traceback__)
                except Exception:
                    logger.debug(
                        "failed to close unavailable MCP client", exc_info=True
                    )
                self.status_message = (
                    f"{self.display_name} MCP is unavailable ({type(exc).__name__})."
                )
                self._status = "unavailable"
                logger.warning(
                    "%s MCP startup failed: %s",
                    self.display_name,
                    type(exc).__name__,
                )
                return False

    async def _discover_tools(self, client: FastMCPClient[Any]) -> list[mcp_types.Tool]:
        try:
            tools = await client.list_tools()
        except Exception:
            logger.warning("%s MCP tools/list failed", self.display_name, exc_info=True)
            return []
        return [tool for tool in tools if _is_read_only_tool(tool.name)]

    async def _discover_prompts(
        self, client: FastMCPClient[Any]
    ) -> list[MCPPromptMetadata]:
        try:
            prompts = await client.list_prompts()
        except Exception:
            logger.warning(
                "%s MCP prompts/list failed", self.display_name, exc_info=True
            )
            return []
        return [
            MCPPromptMetadata(
                name=prompt.name,
                title=prompt.title,
                description=prompt.description,
                required_arguments=tuple(
                    argument.name
                    for argument in prompt.arguments or []
                    if argument.required
                ),
            )
            for prompt in prompts
        ]

    async def _discover_resources(
        self, client: FastMCPClient[Any]
    ) -> list[MCPResourceMetadata]:
        try:
            resources = await client.list_resources()
        except Exception:
            logger.warning(
                "%s MCP resources/list failed", self.display_name, exc_info=True
            )
            return []
        return [
            MCPResourceMetadata(
                uri=str(resource.uri),
                name=resource.name,
                title=resource.title,
                description=resource.description,
                mime_type=resource.mimeType,
            )
            for resource in resources
        ]

    def _build_toolset(self, tools: list[mcp_types.Tool]) -> Toolset:
        haystack_tools: list[Tool] = []
        for metadata in tools:
            tool_name = metadata.name

            async def invoke(
                _tool_name: str = tool_name, **arguments: object
            ) -> object:
                return await self._call_tool(_tool_name, arguments)

            tool = Tool(
                name=tool_name,
                description=metadata.description or metadata.title or tool_name,
                parameters=metadata.inputSchema,
                async_function=invoke,
            )
            setattr(tool, "netai_connector", self.connector)
            setattr(tool, "netai_effect", "read")
            haystack_tools.append(tool)
        return Toolset(haystack_tools)

    async def _call_tool(self, name: str, arguments: dict[str, object]) -> object:
        client = self._client
        if client is None:
            raise RuntimeError(f"{self.display_name} MCP is not connected")
        result = await client.call_tool(name, arguments)
        if result.is_error:
            detail = "\n".join(_dump_content(item) for item in result.content)
            raise RuntimeError(detail or f"MCP tool {name} failed")
        if result.structured_content is not None:
            return _json_compatible(result.structured_content)
        if result.data is not None:
            return _json_compatible(result.data)
        text_items = [
            item.text
            for item in result.content
            if isinstance(item, mcp_types.TextContent)
        ]
        if text_items:
            return "\n".join(text_items)
        return [_dump_content(item) for item in result.content]

    async def get_toolset(self, *, force: bool = False) -> Toolset | None:
        if await self.warm_up(force=force):
            return self._toolset
        return None

    def is_relevant(self, text: str) -> bool:
        """Route using connector identity and metadata advertised by the server."""

        searchable = [self.connector, self.display_name]
        if self._toolset is not None:
            searchable.extend(
                f"{tool.name} {tool.description}" for tool in self._toolset.tools
            )
        searchable.extend(prompt.search_text for prompt in self._prompt_metadata)
        searchable.extend(resource.search_text for resource in self._resource_metadata)
        return any(_relevance_score(text, candidate) > 0 for candidate in searchable)

    async def request_context(self, query: str) -> MCPRequestContext:
        """Fetch only prompt/resource content whose metadata matches this request."""

        if not await self.warm_up():
            return MCPRequestContext()

        prompt = self._best_prompt(query)
        resources = self._best_resources(query, limit=2)
        prompt_task = self._get_prompt(prompt) if prompt is not None else None
        resource_tasks = [self._read_resource(resource) for resource in resources]

        tasks = ([prompt_task] if prompt_task is not None else []) + resource_tasks
        if not tasks:
            return MCPRequestContext()
        results = await asyncio.gather(*tasks, return_exceptions=True)

        prompts: list[MCPPromptContext] = []
        resource_contexts: list[MCPResourceContext] = []
        index = 0
        if prompt is not None:
            prompt_result = results[index]
            index += 1
            if isinstance(prompt_result, str) and prompt_result:
                prompts.append(
                    MCPPromptContext(self.display_name, prompt.name, prompt_result)
                )
            elif isinstance(prompt_result, BaseException):
                logger.warning(
                    "%s MCP prompts/get failed for %s",
                    self.display_name,
                    prompt.name,
                )
        for resource, resource_result in zip(resources, results[index:], strict=True):
            if isinstance(resource_result, str) and resource_result:
                resource_contexts.append(
                    MCPResourceContext(
                        self.display_name,
                        resource.uri,
                        resource.name,
                        resource_result,
                    )
                )
            elif isinstance(resource_result, BaseException):
                logger.warning(
                    "%s MCP resources/read failed for %s",
                    self.display_name,
                    resource.uri,
                )
        return MCPRequestContext(tuple(prompts), tuple(resource_contexts))

    def _best_prompt(self, query: str) -> MCPPromptMetadata | None:
        candidates = [
            (_relevance_score(query, prompt.search_text), prompt)
            for prompt in self._prompt_metadata
            if not prompt.required_arguments
        ]
        if not candidates:
            return None
        score, prompt = max(candidates, key=lambda item: item[0])
        return prompt if score > 0 else None

    def _best_resources(self, query: str, *, limit: int) -> list[MCPResourceMetadata]:
        candidates = sorted(
            (
                (_relevance_score(query, resource.search_text), resource)
                for resource in self._resource_metadata
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        return [resource for score, resource in candidates[:limit] if score > 0]

    async def _get_prompt(self, prompt: MCPPromptMetadata) -> str:
        cached = self._prompt_cache.get(prompt.name)
        if cached is not None:
            return cached
        client = self._client
        if client is None:
            raise RuntimeError(f"{self.display_name} MCP is not connected")
        result = await client.get_prompt(prompt.name)
        parts: list[str] = []
        for message in result.messages:
            content = message.content
            if isinstance(content, mcp_types.TextContent):
                parts.append(f"{message.role}: {content.text}")
            elif isinstance(content, mcp_types.EmbeddedResource):
                resource = content.resource
                if isinstance(resource, mcp_types.TextResourceContents):
                    parts.append(f"{message.role}: {resource.text}")
        text = "\n".join(parts)[: self.config.max_context_chars]
        self._prompt_cache[prompt.name] = text
        return text

    async def _read_resource(self, resource: MCPResourceMetadata) -> str:
        now = monotonic()
        cached = self._resource_cache.get(resource.uri)
        if cached is not None and cached.expires_at > now:
            return cached.text
        client = self._client
        if client is None:
            raise RuntimeError(f"{self.display_name} MCP is not connected")
        contents = await client.read_resource(resource.uri)
        text = "\n".join(
            item.text
            for item in contents
            if isinstance(item, mcp_types.TextResourceContents)
        )[: self.config.max_context_chars]
        self._resource_cache[resource.uri] = _ResourceCacheEntry(
            text=text,
            expires_at=now + self.config.resource_cache_ttl_seconds,
        )
        return text

    async def close(self) -> None:
        async with self._lock:
            client = self._client
            self._client = None
            self._toolset = None
            self._prompt_metadata = ()
            self._resource_metadata = ()
            self._capabilities = MCPCapabilities()
            self._prompt_cache.clear()
            self._resource_cache.clear()
            if client is not None:
                try:
                    await client.__aexit__(None, None, None)
                except Exception as exc:
                    logger.warning(
                        "%s MCP shutdown failed: %s",
                        self.display_name,
                        type(exc).__name__,
                    )
            self.status_message = f"{self.display_name} MCP is closed."
            self._status = "closed"
