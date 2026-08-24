import asyncio
from typing import Any

import pytest
from fastmcp import Client
from haystack.tools import Tool
from pydantic import HttpUrl, ValidationError

from app.mcp.mcp_server import (
    MCPServerConfig,
    SharedTokenVerifier,
    _consumer_access_check,
    create_configured_mcp_server,
    create_mcp_server,
    netai_tool_to_fastmcp,
    validate_mcp_server_configs,
)

LOCAL_CONSUMER_URL = HttpUrl("http://localhost:5173")
EXAMPLE_CONSUMER_URL = HttpUrl("https://consumer.example.com")


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
                    allowed_consumer_urls=(LOCAL_CONSUMER_URL,),
                ),
                MCPServerConfig(
                    name="two",
                    connector="zabbix",
                    description="Second server.",
                    allowed_consumer_urls=(LOCAL_CONSUMER_URL,),
                ),
            ]
        )


def test_mcp_server_config_requires_connector() -> None:
    with pytest.raises(ValueError, match="has no connector"):
        MCPServerConfig(
            name="unnamed-connector",
            connector="",
            description="A server.",
            allowed_consumer_urls=(LOCAL_CONSUMER_URL,),
        )


def test_mcp_server_config_requires_description() -> None:
    with pytest.raises(ValueError, match="has no description"):
        validate_mcp_server_configs(
            [
                MCPServerConfig(
                    name="undocumented",
                    connector="zabbix",
                    description="",
                    allowed_consumer_urls=(LOCAL_CONSUMER_URL,),
                )
            ]
        )


def test_mcp_server_config_rejects_invalid_consumer_url() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(
            name="invalid-url",
            connector="zabbix",
            description="A server.",
            allowed_consumer_urls=("not-a-url",),  # type: ignore[arg-type]
        )


def test_configured_mcp_server_can_select_a_registry_connector(monkeypatch) -> None:
    from app.core.config import project_settings

    monkeypatch.setattr(project_settings, "TOOLS_USE_MOCK_DATA", True)
    monkeypatch.setattr(project_settings, "MCP_CONSUMER_TOKEN", "test-token")
    server = create_configured_mcp_server(
        MCPServerConfig(
            name="SuzieQ",
            connector="suzieq",
            description="Read-only SuzieQ network state.",
            allowed_consumer_urls=(LOCAL_CONSUMER_URL,),
            tool_names=("suzieq_get_devices",),
        )
    )

    assert server.name == "SuzieQ"


def test_consumer_url_authorization_uses_allowlist(monkeypatch) -> None:
    config = MCPServerConfig(
        name="zabbix",
        connector="zabbix",
        description="Read-only Zabbix monitoring.",
        allowed_consumer_urls=(EXAMPLE_CONSUMER_URL,),
    )
    monkeypatch.setattr(
        "app.mcp.mcp_server.get_http_headers",
        lambda: {"origin": "https://consumer.example.com/"},
    )

    assert _consumer_access_check(config)(object()) is True

    monkeypatch.setattr(
        "app.mcp.mcp_server.get_http_headers",
        lambda: {"origin": "https://other.example.com"},
    )
    assert _consumer_access_check(config)(object()) is False


def test_shared_token_verifier_rejects_invalid_tokens() -> None:
    async def exercise() -> None:
        verifier = SharedTokenVerifier("test-token")
        assert await verifier.verify_token("wrong-token") is None
        access_token = await verifier.verify_token("test-token")
        assert access_token is not None
        assert access_token.scopes == ["mcp:read"]

    asyncio.run(exercise())
