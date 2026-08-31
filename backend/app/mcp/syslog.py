"""Failure-isolated network-device syslog MCP capabilities consumed by NetAI."""

from app.mcp.mcp_client import MCPClientConfig, OptionalMCPToolProvider


class SyslogToolProvider(OptionalMCPToolProvider):
    """Name the standalone syslog service at NetAI's composition boundary."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        retry_after_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            config,
            connector="syslog",
            display_name="Syslog intelligence",
            retry_after_seconds=retry_after_seconds,
        )
