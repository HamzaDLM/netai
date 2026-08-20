"""MCP server for NetAI's tools.

NetAI's ``netai_tool`` already contains the callable, name and JSON input schema that MCP
needs, so exposing a NetAI integration only requires passing its tools to ``create_mcp_server``.
"""

import argparse
import asyncio
import inspect
import json
import logging
from collections.abc import Iterable
from importlib import import_module
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from haystack.tools import Tool

from app.core.config import project_settings
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_ZABBIX_TOOLS = (
    "zabbix_get_hosts",
    "zabbix_get_problems",
    "zabbix_diagnose_host",
    "zabbix_get_zabbix_server_status",
)

DEFAULT_MCP_CONFIG = (
    {
        "name": "zabbix",
        "connector": "zabbix",
        "host": "127.0.0.1",
        "port": 8030,
        "transport": "http",
        "use_mock_data": False,
        "tool_names": list(DEFAULT_ZABBIX_TOOLS),
    },
)


def _tool_description(tool: Tool) -> str:
    """Read the MCP description from the Haystack Tool's own metadata."""

    description = getattr(tool, "description", "")
    if isinstance(description, str) and description.strip():
        return description.strip()

    callable_target = tool.async_function or tool.function
    docstring = inspect.getdoc(callable_target) if callable_target else None
    if docstring:
        return docstring.strip()

    return f"Invoke the NetAI tool {tool.name}."


def netai_tool_to_fastmcp(tool: Tool) -> FunctionTool:
    """Expose the same Haystack Tool through the external MCP protocol."""

    async def invoke(**kwargs: Any) -> Any:
        return await tool.invoke_async(**kwargs)

    return FunctionTool(
        name=tool.name,
        description=_tool_description(tool),
        parameters=tool.parameters,
        output_schema=None,
        fn=invoke,
        return_type=Any,
        meta={"source": "netai", "adapter": "haystack"},
    )


def create_mcp_server(
    tools: Iterable[Tool],
    *,
    name: str = "NetAI",
    instructions: str | None = None,
) -> FastMCP:
    """Create an MCP server exposing the supplied NetAI tools and metadata."""

    server = FastMCP(name=name, instructions=instructions)
    for tool in tools:
        server.add_tool(netai_tool_to_fastmcp(tool))
    return server


def _discover_module_tools(module_name: str) -> dict[str, Tool]:
    module = import_module(module_name)
    discovered: dict[str, Tool] = {}
    for value in vars(module).values():
        if isinstance(value, Tool):
            discovered[value.name] = value
    logger.debug("discovered %d tools from module %s", len(discovered), module_name)
    return discovered


def get_zabbix_tools(
    *,
    use_mock_data: bool | None = None,
    tool_names: Iterable[str] | None = DEFAULT_ZABBIX_TOOLS,
) -> list[Tool]:
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
    logger.debug(
        "selected %d Zabbix MCP tools (mock_data=%s)",
        len(selected_names),
        use_mocks,
    )
    return [available[name] for name in selected_names]


def create_zabbix_mcp_server(
    *,
    use_mock_data: bool | None = None,
    tool_names: Iterable[str] | None = DEFAULT_ZABBIX_TOOLS,
    name: str = "NetAI Zabbix",
) -> FastMCP:
    """Build the example read-only Zabbix MCP server."""

    return create_mcp_server(
        get_zabbix_tools(use_mock_data=use_mock_data, tool_names=tool_names),
        name=name,
        instructions=(
            "Read-only Zabbix monitoring tools for host discovery, active problems, "
            "server health, and evidence-based host diagnosis."
        ),
    )


def create_configured_mcp_server(config: dict[str, Any]) -> FastMCP:
    """Create one MCP server from a declarative runtime configuration."""

    name = str(config.get("name", "NetAI Zabbix")).strip() or "NetAI Zabbix"
    connector = str(config.get("connector", "zabbix")).strip().lower()
    tool_names_value = config.get("tool_names")
    tool_names = (
        [str(name) for name in tool_names_value]
        if isinstance(tool_names_value, list)
        else None
    )
    if connector == "zabbix":
        logger.debug(
            "creating MCP server name=%s connector=%s tools=%s",
            name,
            connector,
            len(tool_names) if tool_names is not None else "all",
        )
        return create_zabbix_mcp_server(
            use_mock_data=(
                bool(config["use_mock_data"]) if "use_mock_data" in config else None
            ),
            tool_names=tool_names,
            name=name,
        )

    registry = ToolRegistry(project_settings)
    selected_tools = registry.tools_for(connector, tool_names)
    logger.debug(
        "creating MCP server name=%s connector=%s tools=%s",
        name,
        connector,
        len(selected_tools),
    )
    return create_mcp_server(
        selected_tools,
        name=name,
        instructions=f"Read-only {connector} tools exposed by NetAI.",
    )


def load_mcp_server_config(path: str | None = None) -> list[dict[str, Any]]:
    """Load and validate the list of MCP server instances."""

    if path is None:
        default_configs = [dict(DEFAULT_MCP_CONFIG[0])]
        logger.debug("using default MCP server configuration")
        return default_configs

    logger.info("loading MCP server configuration from %s", path)
    with open(path, encoding="utf-8") as config_file:
        value = json.load(config_file)
    if not isinstance(value, list) or not value:
        raise ValueError("MCP server configuration must be a non-empty JSON list")

    configs: list[dict[str, Any]] = []
    names: set[str] = set()
    endpoints: set[tuple[str, int]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(
                f"MCP server configuration entry {index} must be an object"
            )
        name = str(item.get("name", "")).strip()
        host = str(item.get("host", "127.0.0.1")).strip()
        port = item.get("port")
        transport = str(item.get("transport", "http")).strip()
        if not name:
            raise ValueError(f"MCP server configuration entry {index} has no name")
        if name in names:
            raise ValueError(f"Duplicate MCP server name '{name}'")
        if not host:
            raise ValueError(f"MCP server '{name}' has no host")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"MCP server '{name}' has an invalid port")
        endpoint = (host, port)
        if endpoint in endpoints:
            raise ValueError(f"Duplicate MCP server endpoint '{host}:{port}'")
        if transport not in {"http", "streamable-http", "sse"}:
            raise ValueError(f"MCP server '{name}' has an unsupported transport")
        names.add(name)
        endpoints.add(endpoint)
        configs.append(
            {**item, "name": name, "host": host, "port": port, "transport": transport}
        )
    logger.info("loaded %d MCP server configurations", len(configs))
    return configs


async def _run_mcp_server(server: FastMCP, config: dict[str, Any]) -> None:
    """Run one listener and log failures without hiding them from the supervisor."""

    name = config["name"]
    endpoint = f"{config['host']}:{config['port']}"
    logger.info(
        "starting MCP server name=%s connector=%s transport=%s endpoint=%s",
        name,
        config.get("connector", "zabbix"),
        config["transport"],
        endpoint,
    )
    try:
        await server.run_async(
            transport=config["transport"],
            host=config["host"],
            port=config["port"],
            show_banner=False,
        )
    except asyncio.CancelledError:
        logger.info("stopping MCP server name=%s endpoint=%s", name, endpoint)
        raise
    except Exception:
        logger.exception("mcp server failed name=%s endpoint=%s", name, endpoint)
        raise
    else:
        logger.info("mcp server stopped name=%s endpoint=%s", name, endpoint)


async def run_mcp_servers(configs: Iterable[dict[str, Any]]) -> None:
    """Run all configured MCP servers concurrently under one process."""

    server_configs = list(configs)
    if not server_configs:
        raise ValueError("At least one MCP server must be configured")

    logger.info("starting MCP supervisor with %d server(s)", len(server_configs))
    servers = [create_configured_mcp_server(config) for config in server_configs]
    tasks = [
        asyncio.create_task(
            _run_mcp_server(server, config), name=f"mcp:{config['name']}"
        )
        for server, config in zip(servers, server_configs, strict=True)
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        logger.info("stopping MCP supervisor")
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


# Importable by ASGI/MCP tooling and usable as an in-memory server in tests.
mcp = create_zabbix_mcp_server()


def main() -> None:
    # The MCP module is also launched directly by systemd, outside FastAPI's
    # application bootstrap. Configure a useful default without overriding an
    # application's existing logging configuration.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Run NetAI's Zabbix MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8030, type=int)
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
    parser.add_argument(
        "--config",
        help="Run all MCP servers from a JSON list instead of one Zabbix server",
    )
    args = parser.parse_args()

    if args.config:
        asyncio.run(run_mcp_servers(load_mcp_server_config(args.config)))
        return

    server = create_zabbix_mcp_server(
        use_mock_data=not args.real_data,
        tool_names=None if args.all_tools else DEFAULT_ZABBIX_TOOLS,
    )

    logger.info(
        "starting MCP server name=%s transport=http endpoint=%s:%s",
        server.name,
        args.host,
        args.port,
    )
    server.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
