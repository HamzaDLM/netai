"""Configuration-driven MCP server for NetAI's registered tools."""

import asyncio
import hmac
import inspect
import logging
from collections.abc import Iterable
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, AuthContext, TokenVerifier
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import AuthMiddleware
from fastmcp.tools import FunctionTool
from haystack.tools import Tool
from pydantic import HttpUrl
from pydantic.dataclasses import dataclass

from app.core.config import project_settings
from app.core.logging import configure_logging
from app.tools.registry import ToolRegistry

# Use Uvicorn's error logger so standalone MCP execution and FastAPI share the
# same formatter and handler configuration.
logger = logging.getLogger("uvicorn.error")


MCPTransport = Literal["http", "streamable-http", "sse"]


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    """Configuration for one locally exposed MCP listener."""

    name: str
    connector: str
    description: str
    allowed_consumer_urls: tuple[HttpUrl, ...]
    host: str = "127.0.0.1"
    port: int = 8030
    transport: MCPTransport = "http"
    tool_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("MCP server configuration has no name")
        if not self.connector.strip():
            raise ValueError(f"MCP server '{self.name}' has no connector")
        if not self.description.strip():
            raise ValueError(f"MCP server '{self.name}' has no description")
        if not self.allowed_consumer_urls:
            raise ValueError(f"MCP server '{self.name}' has no consumer URL allowlist")
        if not self.host.strip():
            raise ValueError(f"MCP server '{self.name}' has no host")
        if not 1 <= self.port <= 65535:
            raise ValueError(f"MCP server '{self.name}' has an invalid port")
        if self.transport not in {"http", "streamable-http", "sse"}:
            raise ValueError(f"MCP server '{self.name}' has an unsupported transport")


class SharedTokenVerifier(TokenVerifier):
    """Verify NetAI's shared bearer token without storing it in a token map."""

    def __init__(self, token: str) -> None:
        super().__init__(required_scopes=["mcp:read"])
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        consumer_url = _request_consumer_url()
        if not hmac.compare_digest(token, self._token):
            logger.warning(
                "mcp authentication failed client_id=netai-mcp-consumer url=%s",
                consumer_url or "<missing>",
            )
            return None
        logger.info(
            "mcp authentication succeeded client_id=netai-mcp-consumer url=%s",
            consumer_url or "<missing>",
        )
        return AccessToken(
            token=token,
            client_id="netai-mcp-consumer",
            scopes=["mcp:read"],
        )


# Edit this tuple to choose which local connectors and tools are exposed.
# ``TOOLS_USE_MOCK_DATA`` still controls whether the registry uses mock clients.
MCP_SERVERS: tuple[MCPServerConfig, ...] = (
    MCPServerConfig(
        name="zabbix",
        connector="zabbix",
        description="Read-only Zabbix monitoring, host inventory, and active problem data.",
        allowed_consumer_urls=(HttpUrl("http://localhost:5173"),),
        host="127.0.0.1",
        port=8030,
        transport="http",
        tool_names=(
            "zabbix_get_hosts",
            "zabbix_get_problems",
            "zabbix_diagnose_host",
            "zabbix_get_zabbix_server_status",
        ),
    ),
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
    auth: Any = None,
    middleware: list[Any] | None = None,
) -> FastMCP:
    """Create an MCP server exposing the supplied NetAI tools and metadata."""

    server = FastMCP(
        name=name,
        instructions=instructions,
        auth=auth,
        middleware=middleware,
    )
    for tool in tools:
        server.add_tool(netai_tool_to_fastmcp(tool))
    return server


def _create_token_verifier() -> SharedTokenVerifier:
    token = project_settings.MCP_CONSUMER_TOKEN.strip()
    if not token:
        raise RuntimeError(
            "MCP_CONSUMER_TOKEN must be configured before starting MCP servers"
        )
    return SharedTokenVerifier(token)


def _request_consumer_url() -> str:
    headers = get_http_headers()
    return (headers.get("x-mcp-consumer-url") or headers.get("origin") or "").rstrip(
        "/"
    )


def _consumer_access_check(config: MCPServerConfig):
    allowed_urls = {str(url).rstrip("/") for url in config.allowed_consumer_urls}

    def check(_context: AuthContext) -> bool:
        consumer_url = _request_consumer_url()
        allowed = consumer_url in allowed_urls
        if not allowed:
            logger.warning(
                "mcp consumer authorization failed server name=%s url=%s",
                config.name,
                consumer_url or "<missing>",
            )
        else:
            logger.info(
                "mcp consumer authorized server name=%s connector=%s url=%s",
                config.name,
                config.connector,
                consumer_url,
            )
        return allowed

    return check


def create_configured_mcp_server(config: MCPServerConfig) -> FastMCP:
    """Create one MCP server from a declarative runtime configuration."""

    name = config.name.strip()
    connector = config.connector.strip().lower()
    description = config.description.strip()
    tool_names = list(config.tool_names) or None
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
        instructions=description,
        auth=_create_token_verifier(),
        middleware=[AuthMiddleware(auth=_consumer_access_check(config))],
    )


def validate_mcp_server_configs(
    raw_configs: Iterable[MCPServerConfig],
) -> list[MCPServerConfig]:
    """Validate and normalize the module-level MCP server configuration."""

    names: set[str] = set()
    endpoints: set[tuple[str, int]] = set()
    configs = list(raw_configs)
    if not configs:
        raise ValueError("At least one MCP server must be configured")
    for config in configs:
        if config.name in names:
            raise ValueError(f"Duplicate MCP server name '{config.name}'")
        endpoint = (config.host, config.port)
        if endpoint in endpoints:
            raise ValueError(
                f"Duplicate MCP server endpoint '{config.host}:{config.port}'"
            )
        names.add(config.name)
        endpoints.add(endpoint)
    logger.info("validated %d MCP server configurations", len(configs))
    return configs


async def _run_mcp_server(server: FastMCP, config: MCPServerConfig) -> None:
    """Run one listener and log failures without hiding them from the supervisor."""

    name = config.name
    endpoint = f"{config.host}:{config.port}"
    logger.info(
        "starting MCP server name=%s connector=%s transport=%s endpoint=%s",
        name,
        config.connector,
        config.transport,
        endpoint,
    )
    try:
        await server.run_async(
            transport=config.transport,
            host=config.host,
            port=config.port,
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


async def run_mcp_servers(configs: Iterable[MCPServerConfig]) -> None:
    """Run all configured MCP servers concurrently under one process."""

    configure_logging()
    server_configs = validate_mcp_server_configs(configs)
    if not server_configs:
        raise ValueError("At least one MCP server must be configured")

    logger.info("starting MCP supervisor with %d server(s)", len(server_configs))
    servers = [create_configured_mcp_server(config) for config in server_configs]
    tasks = [
        asyncio.create_task(_run_mcp_server(server, config), name=f"mcp:{config.name}")
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
    # application bootstrap, so initialize the shared logging configuration.
    configure_logging()
    asyncio.run(run_mcp_servers(MCP_SERVERS))


if __name__ == "__main__":
    main()
