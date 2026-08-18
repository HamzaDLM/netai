"""MCP server for NetAI's tools.

NetAI's ``netai_tool`` already contains the callable, name and JSON input schema that MCP
needs, so exposing a NetAI integration only requires passing its tools to ``create_mcp_server``.
"""

import argparse
import inspect
from collections.abc import Callable, Iterable, Mapping
from importlib import import_module
from typing import Any, Protocol

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool

from app.core.config import project_settings


class NetAIToolSchema(Protocol):
    """The small part of Haystack's Tool API required by the MCP bridge."""

    name: str
    description: str
    parameters: dict[str, Any]
    function: Any

    def invoke(self, **kwargs: Any) -> Any: ...


DEFAULT_ZABBIX_TOOLS = (
    "zabbix_get_hosts",
    "zabbix_get_problems",
    "zabbix_diagnose_host",
    "zabbix_get_zabbix_server_status",
)

ZABBIX_TOOL_DESCRIPTIONS = {
    "zabbix_get_hosts": (
        "Find Zabbix hosts by name, group, tags, availability, or maintenance state."
    ),
    "zabbix_get_problems": (
        "List active Zabbix problems, optionally scoped by host, group, severity, "
        "acknowledgement, and lookback window."
    ),
    "zabbix_diagnose_host": (
        "Run a read-only host diagnosis combining status, problems, interfaces, "
        "metrics, and recent events."
    ),
    "zabbix_get_zabbix_server_status": (
        "Return Zabbix API, inventory, alert, queue, and performance health."
    ),
}


def netai_tool_to_fastmcp(
    tool: NetAIToolSchema,
    *,
    description: str | None = None,
) -> FunctionTool:
    """Adapt a NetAI Tool into a FastMCP tool.

    Synchronous infrastructure clients are run in a worker thread so a slow API
    call does not block every other request handled by the MCP server.
    """

    if inspect.iscoroutinefunction(tool.function):

        async def invoke_async(**kwargs: Any) -> Any:
            result = tool.invoke(**kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        invoke: Callable[..., Any] = invoke_async

    else:

        def invoke_sync(**kwargs: Any) -> Any:
            return tool.invoke(**kwargs)

        invoke = invoke_sync

    effective_description = (
        description
        or getattr(tool, "description", "")
        or inspect.getdoc(getattr(tool, "function", None))
        or f"Invoke the NetAI tool {tool.name}."
    )
    return FunctionTool(
        name=tool.name,
        description=effective_description,
        parameters=tool.parameters,
        output_schema=None,
        fn=invoke,
        return_type=Any,
        meta={"source": "netai", "adapter": "haystack"},
    )


def create_mcp_server(
    tools: Iterable[NetAIToolSchema],
    *,
    name: str = "NetAI",
    instructions: str | None = None,
    descriptions: Mapping[str, str] | None = None,
) -> FastMCP:
    """Create an MCP server exposing the supplied NetAI tools."""

    server = FastMCP(name=name, instructions=instructions)
    description_map = descriptions or {}
    for tool in tools:
        server.add_tool(
            netai_tool_to_fastmcp(
                tool,
                description=description_map.get(tool.name),
            )
        )
    return server


def _discover_module_tools(module_name: str) -> dict[str, NetAIToolSchema]:
    module = import_module(module_name)
    discovered: dict[str, NetAIToolSchema] = {}
    for value in vars(module).values():
        if not all(hasattr(value, attr) for attr in ("name", "parameters", "invoke")):
            continue
        name = getattr(value, "name", None)
        if isinstance(name, str):
            discovered[name] = value
    return discovered


def get_zabbix_tools(
    *,
    use_mock_data: bool | None = None,
    tool_names: Iterable[str] | None = DEFAULT_ZABBIX_TOOLS,
) -> list[NetAIToolSchema]:
    """Load selected Zabbix tools from either the real or mock integration."""

    use_mocks = (
        project_settings.TOOLS_USE_MOCK_DATA if use_mock_data is None else use_mock_data
    )
    module_name = (
        "app.tools._zabbix_tools_mock" if use_mocks else "app.tools.zabbix_tools"
    )
    available = _discover_module_tools(module_name)
    selected_names = tuple(tool_names) if tool_names is not None else tuple(available)
    missing = [name for name in selected_names if name not in available]
    if missing:
        raise ValueError(
            f"Unknown Zabbix MCP tool(s): {', '.join(missing)}. "
            f"Available: {', '.join(sorted(available))}"
        )
    return [available[name] for name in selected_names]


def create_zabbix_mcp_server(
    *,
    use_mock_data: bool | None = None,
    tool_names: Iterable[str] | None = DEFAULT_ZABBIX_TOOLS,
) -> FastMCP:
    """Build the example read-only Zabbix MCP server."""

    return create_mcp_server(
        get_zabbix_tools(use_mock_data=use_mock_data, tool_names=tool_names),
        name="NetAI Zabbix",
        instructions=(
            "Read-only Zabbix monitoring tools for host discovery, active problems, "
            "server health, and evidence-based host diagnosis."
        ),
        descriptions=ZABBIX_TOOL_DESCRIPTIONS,
    )


# Importable by ASGI/MCP tooling and usable as an in-memory server in tests.
mcp = create_zabbix_mcp_server()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NetAI's Zabbix MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8030, type=int)
    parser.add_argument("--transport", choices=("http", "stdio"), default="http")
    parser.add_argument(
        "--real-data",
        action="store_true",
        help="Use ZABBIX_API_URL/ZABBIX_API_TOKEN instead of mock data",
    )
    parser.add_argument(
        "--all-tools",
        action="store_true",
        help="Expose every Zabbix tool instead of the curated read-only example set",
    )
    args = parser.parse_args()

    server = create_zabbix_mcp_server(
        use_mock_data=not args.real_data,
        tool_names=None if args.all_tools else DEFAULT_ZABBIX_TOOLS,
    )

    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
