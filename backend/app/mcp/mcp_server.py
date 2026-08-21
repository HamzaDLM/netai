"""Configuration-driven MCP server for NetAI's registered tools."""

import asyncio
import inspect
import logging
from collections.abc import Iterable
from typing import Any

from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from haystack.tools import Tool

from app.core.config import project_settings
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Edit this tuple to choose which local connectors and tools are exposed.
# ``TOOLS_USE_MOCK_DATA`` still controls whether the registry uses mock clients.
MCP_SERVERS: tuple[dict[str, Any], ...] = (
    {
        "name": "zabbix",
        "connector": "zabbix",
        "host": "127.0.0.1",
        "port": 8030,
        "transport": "http",
        "tool_names": (
            "zabbix_get_hosts",
            "zabbix_get_problems",
            "zabbix_diagnose_host",
            "zabbix_get_zabbix_server_status",
        ),
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


def create_configured_mcp_server(config: dict[str, Any]) -> FastMCP:
    """Create one MCP server from a declarative runtime configuration."""

    name = str(config.get("name", "")).strip()
    connector = str(config.get("connector", "")).strip().lower()
    if not name:
        raise ValueError("MCP server configuration has no name")
    if not connector:
        raise ValueError(f"MCP server '{name}' has no connector")
    tool_names_value = config.get("tool_names")
    tool_names = (
        [str(name) for name in tool_names_value]
        if isinstance(tool_names_value, (list, tuple))
        else None
    )
    registry = ToolRegistry(project_settings)
    available_tools = [
        tool
        for tool in registry.tools
        if getattr(tool, "netai_connector", None) == connector
    ]
    if not available_tools:
        raise ValueError(f"Unknown connector '{connector}'")
    if tool_names is None:
        selected_tools = available_tools
    else:
        tools_by_name = {tool.name: tool for tool in available_tools}
        missing = [name for name in tool_names if name not in tools_by_name]
        if missing:
            raise ValueError(
                f"Unknown {connector} MCP tool(s): {', '.join(missing)}. "
                f"Available: {', '.join(sorted(tools_by_name))}"
            )
        selected_tools = [tools_by_name[name] for name in tool_names]
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


def validate_mcp_server_configs(
    raw_configs: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and normalize the module-level MCP server configuration."""

    configs: list[dict[str, Any]] = []
    names: set[str] = set()
    endpoints: set[tuple[str, int]] = set()
    for index, item in enumerate(raw_configs):
        if not isinstance(item, dict):
            raise ValueError(
                f"MCP server configuration entry {index} must be an object"
            )
        name = str(item.get("name", "")).strip()
        connector = str(item.get("connector", "")).strip().lower()
        host = str(item.get("host", "127.0.0.1")).strip()
        port = item.get("port")
        transport = str(item.get("transport", "http")).strip()
        if not name:
            raise ValueError(f"MCP server configuration entry {index} has no name")
        if not connector:
            raise ValueError(f"MCP server '{name}' has no connector")
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
            {
                **item,
                "name": name,
                "connector": connector,
                "host": host,
                "port": port,
                "transport": transport,
            }
        )
    logger.info("validated %d MCP server configurations", len(configs))
    return configs


async def _run_mcp_server(server: FastMCP, config: dict[str, Any]) -> None:
    """Run one listener and log failures without hiding them from the supervisor."""

    name = config["name"]
    endpoint = f"{config['host']}:{config['port']}"
    logger.info(
        "starting MCP server name=%s connector=%s transport=%s endpoint=%s",
        name,
        config["connector"],
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

    server_configs = validate_mcp_server_configs(configs)
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


def main() -> None:
    # The MCP module is also launched directly by systemd, outside FastAPI's
    # application bootstrap. Configure a useful default without overriding an
    # application's existing logging configuration.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_mcp_servers(MCP_SERVERS))


if __name__ == "__main__":
    main()
