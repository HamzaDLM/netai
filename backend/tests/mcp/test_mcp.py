import asyncio
from typing import Any

import pytest
from fastmcp import Client
from haystack.tools import Tool

from app.mcp.mcp_server import (
    DEFAULT_ZABBIX_TOOLS,
    create_configured_mcp_server,
    create_mcp_server,
    create_zabbix_mcp_server,
    get_zabbix_tools,
    load_mcp_server_config,
    netai_tool_to_fastmcp,
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


def test_zabbix_server_exposes_curated_tools() -> None:
    tools = get_zabbix_tools(use_mock_data=True)
    assert [tool.name for tool in tools] == list(DEFAULT_ZABBIX_TOOLS)

    server = create_zabbix_mcp_server(use_mock_data=True)
    assert server.name == "NetAI Zabbix"


def test_mcp_uses_haystack_tool_descriptions() -> None:
    async def exercise() -> None:
        tools = get_zabbix_tools(use_mock_data=False)
        server = create_zabbix_mcp_server(use_mock_data=False)
        async with Client(server) as client:
            definitions = {tool.name: tool for tool in await client.list_tools()}

        assert definitions[tools[0].name].description == tools[0].description

    asyncio.run(exercise())


def test_mcp_falls_back_to_tool_docstring() -> None:
    tool = _documented_tool()

    assert (
        netai_tool_to_fastmcp(tool).description
        == "Return a device name from the documented MCP example tool."
    )


def test_mcp_server_config_rejects_duplicate_endpoints(tmp_path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        "["
        '{"name":"one","connector":"zabbix","host":"127.0.0.1","port":8030},'
        '{"name":"two","connector":"zabbix","host":"127.0.0.1","port":8030}'
        "]",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate MCP server endpoint"):
        load_mcp_server_config(str(config_path))


def test_configured_mcp_server_can_select_a_registry_connector(monkeypatch) -> None:
    from app.core.config import project_settings

    monkeypatch.setattr(project_settings, "TOOLS_USE_MOCK_DATA", True)
    server = create_configured_mcp_server(
        {
            "name": "SuzieQ",
            "connector": "suzieq",
            "tool_names": ["suzieq_get_devices"],
        }
    )

    assert server.name == "SuzieQ"


def test_zabbix_server_rejects_unknown_tool() -> None:
    with pytest.raises(ValueError, match="Unknown Zabbix MCP tool"):
        get_zabbix_tools(use_mock_data=True, tool_names=["not_a_zabbix_tool"])
