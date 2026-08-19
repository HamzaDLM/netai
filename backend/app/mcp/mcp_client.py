"""Configuration adapter for external MCP servers used by Haystack."""

from dataclasses import dataclass
from typing import cast

from haystack.utils.auth import Secret
from haystack_integrations.tools.mcp import MCPToolset, StreamableHttpServerInfo


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
