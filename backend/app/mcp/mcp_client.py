"""Reusable MCP client plus a bridge from remote MCP tools to Haystack tools."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, cast

from fastmcp import Client, FastMCP
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import StreamableHttpTransport
from haystack.utils.auth import Secret
from haystack_integrations.tools.mcp import (
    MCPTool,
    MCPToolset,
    StreamableHttpServerInfo,
)
from mcp.types import Tool as MCPToolDefinition

from app.core.config import project_settings


@dataclass(frozen=True, slots=True)
class MCPClientConfig:
    url: str = "http://127.0.0.1:8030/mcp"
    token: str | None = None
    headers: dict[str, str] | None = None
    timeout: float = 30.0


infrahub_mcp = MCPClientConfig(
    url=project_settings.INFRAHUB_MCP_URL,
    token=project_settings.INFRAHUB_MCP_TOKEN or None,
    timeout=project_settings.INFRAHUB_MCP_TIMEOUT_SECONDS,
)


def get_mcp_client_config(name: str) -> MCPClientConfig | None:
    """Resolve a named MCP configuration declared by this module."""

    value = globals().get(name)
    return value if isinstance(value, MCPClientConfig) else None


def _streamable_http_server_info(
    config: MCPClientConfig,
) -> StreamableHttpServerInfo:
    return StreamableHttpServerInfo(
        url=config.url,
        token=config.token,
        headers=cast(dict[str, str | Secret] | None, config.headers),
        timeout=max(1, int(config.timeout)),
    )


def create_haystack_toolset(
    config: MCPClientConfig,
    *,
    include: set[str] | None = None,
) -> MCPToolset:
    """Build a lazily connected MCP toolset suitable for a Haystack Agent."""

    return MCPToolset(
        server_info=_streamable_http_server_info(config),
        tool_names=sorted(include) if include is not None else None,
        connection_timeout=config.timeout,
        invocation_timeout=config.timeout,
        eager_connect=False,
    )


class NetAIMCPClient:
    """Async MCP discovery/invocation client.

    Use it as an async context manager. ``transport`` may be an HTTP URL, an
    MCP config, or a FastMCP instance (useful for tests and embedded servers).
    """

    def __init__(
        self,
        transport: str | dict[str, Any] | FastMCP,
        *,
        token: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> None:
        resolved_transport: Any = transport
        client_auth = token
        if (
            headers
            and isinstance(transport, str)
            and transport.startswith(("http://", "https://"))
        ):
            resolved_transport = StreamableHttpTransport(
                url=transport,
                headers=headers,
                auth=token,
            )
            client_auth = None
        self._client = Client(
            resolved_transport,
            auth=client_auth,
            timeout=timeout,
        )
        self._connected = False

    async def __aenter__(self) -> NetAIMCPClient:
        await self._client.__aenter__()
        self._connected = True
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            await self._client.__aexit__(exc_type, exc, traceback)
        finally:
            self._connected = False

    def _require_connection(self) -> None:
        if not self._connected:
            raise RuntimeError("MCP client must be used inside 'async with'")

    async def list_tools(self) -> list[MCPToolDefinition]:
        self._require_connection()
        return await self._client.list_tools()

    async def call_tool_result(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Call a tool and retain the complete MCP result envelope."""

        self._require_connection()
        result = await self._client.call_tool(name, arguments or {})
        if not isinstance(result, CallToolResult):  # task mode is never requested
            raise TypeError(f"Unexpected MCP result type: {type(result).__name__}")
        return result

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool and return its decoded value."""

        result = await self.call_tool_result(name, arguments)
        if result.data is not None:
            return result.data
        if result.structured_content is not None:
            return result.structured_content
        return [
            block.model_dump(mode="json") if hasattr(block, "model_dump") else block
            for block in result.content
        ]


async def discover_haystack_tools(
    config: MCPClientConfig,
    *,
    include: set[str] | None = None,
) -> list[MCPTool]:
    """Discover an HTTP MCP server and return Agent-ready Haystack MCPTool objects.

    The returned tools own lazy connections; callers should call ``close()`` on
    them when their agent/application shuts down.
    """

    async with NetAIMCPClient(
        config.url,
        token=config.token,
        headers=config.headers,
        timeout=config.timeout,
    ) as client:
        remote_tools = await client.list_tools()

    server_info = _streamable_http_server_info(config)
    return [
        MCPTool(
            name=tool.name,
            description=tool.description,
            server_info=server_info,
            connection_timeout=max(1, int(config.timeout)),
            invocation_timeout=max(1, int(config.timeout)),
        )
        for tool in remote_tools
        if include is None or tool.name in include
    ]


async def _run_cli() -> None:
    parser = argparse.ArgumentParser(description="Discover or call an MCP tool")
    parser.add_argument("--url", default="http://127.0.0.1:8030/mcp")
    parser.add_argument("--token", default=None)
    parser.add_argument("tool", nargs="?", help="Tool name; omit to list tools")
    parser.add_argument(
        "arguments",
        nargs="?",
        default="{}",
        help='Tool arguments as JSON, e.g. \'{"status":"down"}\'',
    )
    args = parser.parse_args()

    async with NetAIMCPClient(args.url, token=args.token) as client:
        if not args.tool:
            tools = await client.list_tools()
            print(
                json.dumps(
                    [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.inputSchema,
                        }
                        for tool in tools
                    ],
                    indent=2,
                )
            )
            return

        arguments = json.loads(args.arguments)
        if not isinstance(arguments, dict):
            raise ValueError("arguments must decode to a JSON object")
        print(json.dumps(await client.call_tool(args.tool, arguments), indent=2))


def main() -> None:
    import asyncio

    asyncio.run(_run_cli())


if __name__ == "__main__":
    main()
