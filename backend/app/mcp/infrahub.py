"""Optional Infrahub MCP tools for the internal NetAI agent.

Infrahub is genuinely external to NetAI, so MCP is appropriate at this boundary.
The connector is lazy and failure-isolated: a missing Infrahub deployment never
prevents the application or an unrelated Agent request from running.
"""

from __future__ import annotations

import asyncio
import logging
import re
from time import monotonic

from haystack_integrations.tools.mcp import MCPToolset

from app.mcp.mcp_client import MCPClientConfig, create_haystack_toolset

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
_RELEVANT_TERMS = (
    "infrahub",
    "source of truth",
    "source-of-truth",
    "intended state",
    "intent data",
)


def _is_read_only_tool(name: str) -> bool:
    words = set(filter(None, re.split(r"[^a-z0-9]+", name.lower())))
    return not bool(words & _MUTATION_TERMS)


class InfrahubToolProvider:
    """Lazily connect to Infrahub and cache its read-only MCP toolset."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        retry_after_seconds: float = 30.0,
    ) -> None:
        self.config = config
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        self.status = "not_checked"
        self.status_message = "Infrahub is connected only when it is needed."
        self._toolset: MCPToolset | None = None
        self._last_attempt = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def is_relevant(text: str) -> bool:
        normalized = text.casefold()
        return any(term in normalized for term in _RELEVANT_TERMS)

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
                # mcp-haystack currently exposes a synchronous warm_up API. It owns
                # its worker thread, so this one boundary is dispatched away from
                # FastAPI's event loop rather than wrapping native-async clients.
                await asyncio.to_thread(candidate.warm_up)
                safe_tools = [
                    remote_tool
                    for remote_tool in candidate.tools
                    if _is_read_only_tool(remote_tool.name)
                ]
                blocked_count = len(candidate.tools) - len(safe_tools)
                candidate.tools = safe_tools
                for remote_tool in candidate.tools:
                    setattr(remote_tool, "netai_connector", "infrahub")
                    setattr(remote_tool, "netai_effect", "read_only")
                self._toolset = candidate
                self.status = "available"
                self.status_message = (
                    f"Discovered {len(safe_tools)} read-only Infrahub tools"
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
                    logger.debug("Failed to close unavailable Infrahub toolset")
                self.status = "unavailable"
                self.status_message = "Infrahub is currently unavailable."
                logger.warning(
                    "Optional Infrahub MCP connector unavailable (%s)",
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
                    "Infrahub MCP connector close failed (%s)", type(exc).__name__
                )
