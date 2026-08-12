import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.mcp.mcp_client import NetAIMCPClient
from app.mcp.mcp_server import (
    DEFAULT_ZABBIX_TOOLS,
    create_mcp_server,
    create_zabbix_mcp_server,
    get_zabbix_tools,
)


async def _async_echo(device: str) -> dict[str, Any]:
    return {"device": device, "reachable": True}


class _AsyncEchoTool:
    name = "echo_device"
    description = "Echo a device name."
    parameters = {
        "type": "object",
        "properties": {"device": {"type": "string"}},
        "required": ["device"],
    }

    def __init__(self) -> None:
        self.function: Callable[..., Awaitable[dict[str, Any]]] = _async_echo

    def invoke(self, **kwargs: Any) -> Awaitable[dict[str, Any]]:
        return self.function(**kwargs)


def _echo_tool() -> _AsyncEchoTool:
    return _AsyncEchoTool()


def test_server_preserves_haystack_schema_and_returns_structured_data() -> None:
    async def exercise() -> None:
        server = create_mcp_server([_echo_tool()], name="test")
        async with NetAIMCPClient(server) as client:
            definitions = await client.list_tools()
            assert [tool.name for tool in definitions] == ["echo_device"]
            assert definitions[0].inputSchema["required"] == ["device"]
            assert await client.call_tool("echo_device", {"device": "edge-01"}) == {
                "device": "edge-01",
                "reachable": True,
            }

    asyncio.run(exercise())


def test_client_requires_context_manager() -> None:
    async def exercise() -> None:
        client = NetAIMCPClient(create_mcp_server([_echo_tool()]))
        with pytest.raises(RuntimeError, match="async with"):
            await client.list_tools()

    asyncio.run(exercise())


def test_zabbix_server_exposes_curated_tools() -> None:
    tools = get_zabbix_tools(use_mock_data=True)
    assert [tool.name for tool in tools] == list(DEFAULT_ZABBIX_TOOLS)

    server = create_zabbix_mcp_server(use_mock_data=True)
    assert server.name == "NetAI Zabbix"


def test_zabbix_server_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError, match="Unknown Zabbix MCP tool"):
        get_zabbix_tools(use_mock_data=True, tool_names=["not_a_zabbix_tool"])
