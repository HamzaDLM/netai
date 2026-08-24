"""Configuration and lifecycle support for external MCP tool providers."""

import asyncio
import logging
import re
from dataclasses import dataclass
from time import monotonic
from typing import cast

from haystack.utils.auth import Secret
from haystack_integrations.tools.mcp import MCPToolset, StreamableHttpServerInfo

logger = logging.getLogger(__name__)

_MUTATION_TERMS = {
    "add",
    "approve",
    "commit",
    "create",
    "delete",
    "edit",
    "merge",
    "mutate",
    "patch",
    "push",
    "remove",
    "set",
    "update",
    "write",
}


@dataclass(frozen=True, slots=True)
class MCPClientConfig:
    url: str
    token: str | None = None
    headers: dict[str, str] | None = None
    timeout: float = 30.0


def create_haystack_toolset(
    config: MCPClientConfig,
    *,
    include: set[str] | None = None,
) -> MCPToolset:
    """Create Haystack's native lazy MCP toolset for one external server."""

    server_info = StreamableHttpServerInfo(
        url=config.url,
        token=config.token,
        headers=cast(dict[str, str | Secret] | None, config.headers),
        timeout=max(1, int(config.timeout)),
    )
    return MCPToolset(
        server_info=server_info,
        tool_names=sorted(include) if include is not None else None,
        connection_timeout=config.timeout,
        invocation_timeout=config.timeout,
        eager_connect=False,
    )


def _is_read_only_tool(name: str) -> bool:
    words = set(filter(None, re.split(r"[^a-z0-9]+", name.lower())))
    return not bool(words & _MUTATION_TERMS)


class OptionalMCPToolProvider:
    """Lazily discover and cache one failure-isolated read-only MCP toolset."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        connector: str,
        display_name: str,
        relevant_terms: tuple[str, ...],
        retry_after_seconds: float = 30.0,
    ) -> None:
        self.config = config
        self.connector = connector
        self.display_name = display_name
        self.relevant_terms = tuple(term.casefold() for term in relevant_terms)
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        self.status = "not_checked"
        self.status_message = f"{display_name} is connected only when it is needed."
        self._toolset: MCPToolset | None = None
        self._last_attempt = 0.0
        self._lock = asyncio.Lock()

    def is_relevant(self, text: str) -> bool:
        normalized = text.casefold()
        return any(term in normalized for term in self.relevant_terms)

    @property
    def toolset(self) -> MCPToolset | None:
        return self._toolset

    async def get_toolset(self, *, force: bool = False) -> MCPToolset | None:
        if self._toolset is not None:
            return self._toolset
        if (
            not force
            and self.status == "unavailable"
            and monotonic() - self._last_attempt < self.retry_after_seconds
        ):
            return None

        async with self._lock:
            if self._toolset is not None:
                return self._toolset
            if (
                not force
                and self.status == "unavailable"
                and monotonic() - self._last_attempt < self.retry_after_seconds
            ):
                return None

            self._last_attempt = monotonic()
            candidate = create_haystack_toolset(self.config)
            try:
                # mcp-haystack currently owns a worker thread behind its synchronous
                # lifecycle API, so keep this boundary off FastAPI's event loop.
                await asyncio.to_thread(candidate.warm_up)
                safe_tools = [
                    remote_tool
                    for remote_tool in candidate.tools
                    if _is_read_only_tool(remote_tool.name)
                ]
                blocked_count = len(candidate.tools) - len(safe_tools)
                candidate.tools = safe_tools
                for remote_tool in candidate.tools:
                    setattr(remote_tool, "netai_connector", self.connector)
                    setattr(remote_tool, "netai_effect", "read_only")
                self._toolset = candidate
                self.status = "available"
                self.status_message = (
                    f"Discovered {len(safe_tools)} read-only {self.display_name} tools"
                    + (
                        f"; hid {blocked_count} mutating tools."
                        if blocked_count
                        else "."
                    )
                )
                logger.info(self.status_message)
                return candidate
            except Exception as exc:
                try:
                    await asyncio.to_thread(candidate.close)
                except Exception:
                    logger.debug(
                        "failed to close unavailable %s MCP toolset",
                        self.display_name,
                    )
                self.status = "unavailable"
                self.status_message = f"{self.display_name} is currently unavailable."
                logger.warning(
                    "optional %s MCP connector unavailable (%s)",
                    self.display_name,
                    type(exc).__name__,
                )
                return None

    async def close(self) -> None:
        toolset = self._toolset
        self._toolset = None
        if toolset is not None:
            try:
                await asyncio.to_thread(toolset.close)
            except Exception as exc:
                logger.warning(
                    "%s MCP connector close failed (%s)",
                    self.display_name,
                    type(exc).__name__,
                )
