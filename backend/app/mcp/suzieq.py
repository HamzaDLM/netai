"""Failure-isolated SuzieQ MCP capabilities consumed by NetAI."""

from app.mcp.mcp_client import MCPClientConfig, OptionalMCPToolProvider

TOOL_GROUP_PROMPT = """
SuzieQ MCP provides observed network state through the external server's advertised
read-only tools. Use its discovered tool descriptions and begin with namespace and
device identity when those dimensions are available. Query the narrowest relevant
state for interfaces, neighbors, routing, forwarding, or control-plane health. Treat
missing data as absence from the collected dataset rather than proof that an object
never existed. Correlate observed state with intended Infrahub/configuration data,
monitoring, and timestamps when determining impact or cause.
""".strip()


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
            tool_group_prompt=TOOL_GROUP_PROMPT,
            retry_after_seconds=retry_after_seconds,
        )
