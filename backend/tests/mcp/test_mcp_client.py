from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastmcp import Client as FastMCPClient
from fastmcp import FastMCP
from fastmcp.client.client import CallToolResult
from mcp import types as mcp_types
from pydantic import AnyUrl

from app.mcp.mcp_client import MCPClientConfig, OptionalMCPToolProvider


class FakeMCPClient:
    def __init__(
        self,
        *,
        tools: bool = False,
        prompts: bool = False,
        resources: bool = False,
        fail_connect: bool = False,
    ) -> None:
        self.supports_tools = tools
        self.supports_prompts = prompts
        self.supports_resources = resources
        self.fail_connect = fail_connect
        self.closed = False
        self.calls = {
            "tools/list": 0,
            "tools/call": 0,
            "prompts/list": 0,
            "prompts/get": 0,
            "resources/list": 0,
            "resources/read": 0,
        }
        self.initialize_result = SimpleNamespace(
            capabilities=SimpleNamespace(
                tools=object() if tools else None,
                prompts=object() if prompts else None,
                resources=object() if resources else None,
            )
        )

    async def __aenter__(self) -> FakeMCPClient:
        if self.fail_connect:
            raise ConnectionError("unavailable")
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.closed = True

    async def list_tools(self) -> list[mcp_types.Tool]:
        assert self.supports_tools
        self.calls["tools/list"] += 1
        return [
            mcp_types.Tool(
                name="inspect_routing",
                description="Inspect routing state for a device",
                inputSchema={
                    "type": "object",
                    "properties": {"device": {"type": "string"}},
                    "required": ["device"],
                },
            ),
            mcp_types.Tool(
                name="update_routing",
                description="Mutate routing state",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    async def call_tool(
        self, name: str, arguments: dict[str, object]
    ) -> CallToolResult:
        assert self.supports_tools
        self.calls["tools/call"] += 1
        return CallToolResult(
            content=[],
            structured_content={"name": name, **arguments},
            meta=None,
        )

    async def list_prompts(self) -> list[mcp_types.Prompt]:
        assert self.supports_prompts
        self.calls["prompts/list"] += 1
        return [
            mcp_types.Prompt(
                name="routing_diagnostic",
                description="Instructions for diagnosing routing behavior",
            ),
            mcp_types.Prompt(
                name="unrelated_wireless",
                description="Instructions for wireless access points",
            ),
            mcp_types.Prompt(
                name="site_specific",
                description="Instructions requiring a site argument",
                arguments=[mcp_types.PromptArgument(name="site", required=True)],
            ),
        ]

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> mcp_types.GetPromptResult:
        assert self.supports_prompts
        assert arguments is None
        self.calls["prompts/get"] += 1
        return mcp_types.GetPromptResult(
            messages=[
                mcp_types.PromptMessage(
                    role="user",
                    content=mcp_types.TextContent(
                        type="text", text=f"Apply the {name} workflow"
                    ),
                )
            ]
        )

    async def list_resources(self) -> list[mcp_types.Resource]:
        assert self.supports_resources
        self.calls["resources/list"] += 1
        return [
            mcp_types.Resource(
                uri=AnyUrl("schema://inventory"),
                name="inventory_schema",
                description="Inventory schema for routing devices",
                mimeType="text/plain",
            ),
            mcp_types.Resource(
                uri=AnyUrl("docs://wireless"),
                name="wireless_guide",
                description="Wireless access point guide",
                mimeType="text/plain",
            ),
        ]

    async def read_resource(self, uri: str) -> list[mcp_types.ResourceContents]:
        assert self.supports_resources
        self.calls["resources/read"] += 1
        return [
            mcp_types.TextResourceContents(
                uri=AnyUrl(uri),
                mimeType="text/plain",
                text=f"resource body for {uri}",
            )
        ]


class FailingToolCallClient(FakeMCPClient):
    async def call_tool(
        self, name: str, arguments: dict[str, object]
    ) -> CallToolResult:
        self.calls["tools/call"] += 1
        raise ConnectionError("session closed")


class FailingToolDiscoveryClient(FakeMCPClient):
    async def list_tools(self) -> list[mcp_types.Tool]:
        self.calls["tools/list"] += 1
        raise ConnectionError("metadata request failed")


def make_provider(
    client: FakeMCPClient, *, resource_ttl: float = 60.0
) -> OptionalMCPToolProvider:
    return OptionalMCPToolProvider(
        MCPClientConfig(
            url="http://example.test/mcp",
            resource_cache_ttl_seconds=resource_ttl,
        ),
        connector="example",
        display_name="Example",
        tool_group_prompt="Use Example as observed routing state.",
        client_factory=lambda _config: client,  # type: ignore[arg-type,return-value]
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("has_tools", "has_prompts", "has_resources"),
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, False),
        (True, False, True),
        (False, True, True),
        (True, True, True),
    ],
)
async def test_capabilities_discover_metadata_and_fetch_content_on_demand(
    has_tools: bool,
    has_prompts: bool,
    has_resources: bool,
) -> None:
    client = FakeMCPClient(
        tools=has_tools,
        prompts=has_prompts,
        resources=has_resources,
    )
    provider = make_provider(client)

    assert await provider.warm_up() is True
    assert provider.capabilities.tools is has_tools
    assert provider.capabilities.prompts is has_prompts
    assert provider.capabilities.resources is has_resources
    assert len(provider.toolset.tools if provider.toolset else []) == int(has_tools)
    assert len(provider.prompt_metadata) == (3 if has_prompts else 0)
    assert len(provider.resource_metadata) == (2 if has_resources else 0)
    assert client.calls["prompts/get"] == 0
    assert client.calls["resources/read"] == 0

    context = await provider.request_context(
        "diagnose routing behavior using the inventory schema"
    )

    assert len(context.prompts) == int(has_prompts)
    assert len(context.resources) == int(has_resources)
    assert "wireless" not in " ".join(item.text for item in context.prompts)
    assert "wireless" not in " ".join(item.text for item in context.resources)
    assert client.calls["prompts/get"] == int(has_prompts)
    assert client.calls["resources/read"] == int(has_resources)

    await provider.request_context(
        "diagnose routing behavior using the inventory schema"
    )
    assert client.calls["prompts/get"] == int(has_prompts)
    assert client.calls["resources/read"] == int(has_resources)
    await provider.close()
    assert client.closed is True


@pytest.mark.anyio
async def test_tools_only_server_exposes_callable_read_only_tool() -> None:
    client = FakeMCPClient(tools=True)
    provider = make_provider(client)

    toolset = await provider.get_toolset()

    assert toolset is not None
    assert [tool.name for tool in toolset.tools] == ["inspect_routing"]
    assert (
        getattr(toolset.tools[0], "netai_group_prompt", None)
        == "Use Example as observed routing state."
    )
    result = await toolset.tools[0].invoke_async(device="edge-01")
    assert result == {"name": "inspect_routing", "device": "edge-01"}
    assert client.calls["tools/call"] == 1
    await provider.close()


@pytest.mark.anyio
async def test_resource_content_expires_after_configured_ttl() -> None:
    client = FakeMCPClient(resources=True)
    provider = make_provider(client, resource_ttl=0)

    await provider.request_context("inventory schema")
    await provider.request_context("inventory schema")

    assert client.calls["resources/read"] == 2
    await provider.close()


@pytest.mark.anyio
async def test_connection_failure_is_cached_and_does_not_raise() -> None:
    client = FakeMCPClient(fail_connect=True)
    provider = make_provider(client)

    assert await provider.get_toolset() is None
    assert await provider.get_toolset() is None
    assert provider.status == "unavailable"
    assert "unavailable" in provider.status_message
    assert client.closed is True


@pytest.mark.anyio
async def test_tool_call_reconnects_once_after_transport_failure() -> None:
    failed_client = FailingToolCallClient(tools=True)
    recovered_client = FakeMCPClient(tools=True)
    clients = iter((failed_client, recovered_client))
    provider = OptionalMCPToolProvider(
        MCPClientConfig(url="http://example.test/mcp"),
        connector="example",
        display_name="Example",
        client_factory=lambda _config: next(clients),  # type: ignore[arg-type,return-value]
    )

    toolset = await provider.get_toolset()
    assert toolset is not None
    result = await toolset.tools[0].invoke_async(device="edge-01")

    assert result == {"name": "inspect_routing", "device": "edge-01"}
    assert failed_client.calls["tools/call"] == 1
    assert failed_client.closed is True
    assert recovered_client.calls["tools/call"] == 1
    assert provider.status == "available"
    await provider.close()


@pytest.mark.anyio
async def test_concurrent_transport_failures_share_one_reconnected_client() -> None:
    failed_client = FailingToolCallClient(tools=True)
    recovered_client = FakeMCPClient(tools=True)
    clients = iter((failed_client, recovered_client))
    provider = OptionalMCPToolProvider(
        MCPClientConfig(url="http://example.test/mcp"),
        connector="example",
        display_name="Example",
        client_factory=lambda _config: next(clients),  # type: ignore[arg-type,return-value]
    )
    toolset = await provider.get_toolset()
    assert toolset is not None

    results = await asyncio.gather(
        toolset.tools[0].invoke_async(device="edge-01"),
        toolset.tools[0].invoke_async(device="edge-02"),
    )

    assert results == [
        {"name": "inspect_routing", "device": "edge-01"},
        {"name": "inspect_routing", "device": "edge-02"},
    ]
    assert recovered_client.calls["tools/call"] == 2
    await provider.close()


@pytest.mark.anyio
async def test_degraded_metadata_discovery_is_retried() -> None:
    degraded_client = FailingToolDiscoveryClient(tools=True)
    recovered_client = FakeMCPClient(tools=True)
    clients = iter((degraded_client, recovered_client))
    provider = OptionalMCPToolProvider(
        MCPClientConfig(url="http://example.test/mcp"),
        connector="example",
        display_name="Example",
        retry_after_seconds=0,
        client_factory=lambda _config: next(clients),  # type: ignore[arg-type,return-value]
    )

    assert await provider.warm_up() is True
    assert provider.status == "degraded"
    assert provider.toolset is not None
    assert len(provider.toolset.tools) == 0

    toolset = await provider.get_toolset()

    assert toolset is not None
    assert [tool.name for tool in toolset.tools] == ["inspect_routing"]
    assert degraded_client.closed is True
    assert provider.status == "available"
    await provider.close()


@pytest.mark.anyio
async def test_provider_uses_real_fastmcp_tools_prompts_and_resources() -> None:
    server = FastMCP("consumed-server")
    content_calls = {"prompt": 0, "resource": 0}

    @server.tool
    async def inspect_routing(device: str) -> dict[str, str]:
        """Inspect routing state for a device."""

        return {"device": device}

    @server.prompt(name="routing_diagnostic", description="Routing diagnostic steps")
    async def routing_prompt() -> str:
        content_calls["prompt"] += 1
        return "Inspect the route table."

    @server.resource(
        "schema://inventory",
        name="inventory_schema",
        description="Inventory routing schema",
    )
    async def inventory_schema() -> str:
        content_calls["resource"] += 1
        return "device -> route"

    provider = OptionalMCPToolProvider(
        MCPClientConfig(url="http://unused.test/mcp"),
        connector="example",
        display_name="Example",
        client_factory=lambda _config: FastMCPClient(server),  # type: ignore[arg-type,return-value]
    )

    assert await provider.warm_up() is True
    assert content_calls == {"prompt": 0, "resource": 0}
    assert provider.toolset is not None
    tool_result = await provider.toolset.tools[0].invoke_async(device="edge-01")
    context = await provider.request_context("routing diagnostic inventory schema")

    assert tool_result == {"device": "edge-01"}
    assert context.prompts[0].name == "routing_diagnostic"
    assert "route table" in context.prompts[0].text
    assert context.resources[0].uri == "schema://inventory"
    assert context.resources[0].text == "device -> route"
    assert content_calls == {"prompt": 1, "resource": 1}
    await provider.close()
