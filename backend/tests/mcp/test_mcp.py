import asyncio
from typing import Any

import pytest
from fastmcp import Client
from haystack.tools import Tool

from app.mcp.mcp_server import (
    MCPServerConfig,
    create_configured_mcp_server,
    create_mcp_server,
    netai_tool_to_fastmcp,
    validate_mcp_server_configs,
)


async def _async_echo(device: str) -> dict[str, Any]:
    return {"device": device, "reachable": True}


def _echo_tool() -> Tool:
    return Tool(
        name="echo_device",
        description="Echo a device name.",
        parameters={
            "type": "object",
            "properties": {"device": {"type": "string"}},
            "required": ["device"],
        },
        async_function=_async_echo,
    )


def _documented_tool() -> Tool:
    async def invoke(device: str) -> dict[str, str]:
        """Return a device name from the documented MCP example tool."""

        return {"device": device}

    return Tool(
        name="documented_device",
        description="",
        parameters={
            "type": "object",
            "properties": {"device": {"type": "string"}},
            "required": ["device"],
        },
        async_function=invoke,
    )


def test_server_preserves_haystack_schema_and_returns_structured_data() -> None:
    async def exercise() -> None:
        server = create_mcp_server([_echo_tool()], name="test")
        async with Client(server) as client:
            definitions = await client.list_tools()
            assert [tool.name for tool in definitions] == ["echo_device"]
            assert definitions[0].inputSchema["required"] == ["device"]
            result = await client.call_tool("echo_device", {"device": "edge-01"})
            assert result.data == {
                "device": "edge-01",
                "reachable": True,
            }

    asyncio.run(exercise())


def test_configured_server_uses_registered_tool_descriptions(monkeypatch) -> None:
    async def exercise() -> None:
        from app.core.config import project_settings

        monkeypatch.setattr(project_settings, "TOOLS_USE_MOCK_DATA", True)
        server = create_configured_mcp_server(
            MCPServerConfig(
                name="zabbix",
                connector="zabbix",
                description="Read-only Zabbix monitoring tools.",
                tool_names=("zabbix_get_hosts",),
            )
        )
        async with Client(server) as client:
            definitions = {tool.name: tool for tool in await client.list_tools()}

        assert definitions["zabbix_get_hosts"].description.startswith("[Zabbix]")

    asyncio.run(exercise())


def test_mcp_falls_back_to_tool_docstring() -> None:
    tool = _documented_tool()

    assert (
        netai_tool_to_fastmcp(tool).description
        == "Return a device name from the documented MCP example tool."
    )


def test_mcp_server_config_rejects_duplicate_endpoints() -> None:
    with pytest.raises(ValueError, match="Duplicate MCP server endpoint"):
        validate_mcp_server_configs(
            [
                MCPServerConfig(
                    name="one",
                    connector="zabbix",
                    description="First server.",
                ),
                MCPServerConfig(
                    name="two",
                    connector="zabbix",
                    description="Second server.",
                ),
            ]
        )


def test_mcp_server_config_requires_connector() -> None:
    with pytest.raises(ValueError, match="has no connector"):
        MCPServerConfig(
            name="unnamed-connector",
            connector="",
            description="A server.",
        )


def test_mcp_server_config_requires_description() -> None:
    with pytest.raises(ValueError, match="has no description"):
        validate_mcp_server_configs(
            [
                MCPServerConfig(
                    name="undocumented",
                    connector="zabbix",
                    description="",
                )
            ]
        )


def test_configured_mcp_server_can_select_a_registry_connector(monkeypatch) -> None:
    from app.core.config import project_settings

    monkeypatch.setattr(project_settings, "TOOLS_USE_MOCK_DATA", True)
    server = create_configured_mcp_server(
        MCPServerConfig(
            name="SuzieQ",
            connector="suzieq",
            description="Read-only SuzieQ network state.",
            tool_names=("suzieq_get_devices",),
        )
    )

    assert server.name == "SuzieQ"
