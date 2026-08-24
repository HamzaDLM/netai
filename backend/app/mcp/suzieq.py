"""Failure-isolated SuzieQ MCP capabilities consumed by NetAI."""

from app.mcp.mcp_client import MCPClientConfig, OptionalMCPToolProvider


class SuzieQToolProvider(OptionalMCPToolProvider):
    """Name the generic consumed-MCP provider at the composition boundary."""

    def __init__(
        self,
        config: MCPClientConfig,
        *,
        retry_after_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            config,
            connector="suzieq",
            display_name="SuzieQ",
            retry_after_seconds=retry_after_seconds,
        )
